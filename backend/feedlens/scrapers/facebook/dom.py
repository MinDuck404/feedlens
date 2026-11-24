"""Facebook DOM extraction, expansion and scroll waits."""
from __future__ import annotations

from feedlens.scrapers.scripts import load_script
from feedlens.scrapers.facebook.selectors import SELECTORS, FB_NODE_SELECTOR, FB_LINK_SELECTOR, NODE_MARKER

FB_SCROLL_POSITION_JS = load_script("feedlens.scrapers.facebook", 'scroll_position.js', SELECTORS)
FB_CLEAR_MARKERS_JS = load_script("feedlens.scrapers.facebook", 'clear_markers.js', SELECTORS)
FB_RESTORE_SCROLL_JS = load_script("feedlens.scrapers.facebook", 'restore_scroll.js', SELECTORS)
FB_HOVER_LINKS_JS = load_script("feedlens.scrapers.facebook", 'hover_links.js', SELECTORS)
FB_WAIT_FOR_STORY_JS = load_script("feedlens.scrapers.facebook", 'wait_for_story.js', SELECTORS)

import json
import os
import time
from html import escape
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from feedlens.core.models import RawPost
from feedlens.scrapers.facebook.links import clean_facebook_author
from feedlens.scrapers.facebook.links import facebook_ad_link
from feedlens.scrapers.facebook.links import facebook_dom_permalink
from feedlens.scrapers.facebook.links import is_facebook_content_url
from feedlens.scrapers.facebook.links import select_facebook_link
from feedlens.scrapers.facebook.stories import FacebookStoryCache
from feedlens.scrapers.facebook.stories import _extract_facebook_post_id
from feedlens.scrapers.facebook.stories import _facebook_story_belongs_to_group
from feedlens.scrapers.facebook.stories import _match_facebook_story_by_id
from feedlens.scrapers.facebook.stories import match_facebook_story






FB_SCROLL_MESSAGES_JS = load_script("feedlens.scrapers.facebook", 'scroll_messages.js', SELECTORS)


FB_JS = load_script("feedlens.scrapers.facebook", 'extract.js', SELECTORS)


FB_HEADER_SNAPSHOT_JS = load_script("feedlens.scrapers.facebook", 'header_snapshot.js', SELECTORS)


def _facebook_items(page: Page, stories: dict | None = None) -> list[dict]:
    items = page.evaluate(FB_JS)
    skip_keys = getattr(stories, "skip_keys", None) if stories is not None else None
    if stories or skip_keys:
        for item in items:
            dom_url = item.get("url") or facebook_dom_permalink(item.get("links", []), item.get("_author_url", ""))
            raw = RawPost(
                platform="facebook",
                source="",
                author=item.get("author", ""),
                text=item.get("text", ""),
                url=dom_url,
                posted_at=item.get("posted_at", ""),
                sponsored=bool(item.get("sponsored", False)),
            )
            item["url"] = dom_url
            if stories:
                network = match_facebook_story(raw, stories)
                if network is None:
                    network = _match_facebook_story_by_id(_extract_facebook_post_id(dom_url), stories)
                    if network:
                        # ID match can skip link work, but text replacement still needs text corroboration.
                        item["_skip_link_resolve"] = True
                if network:
                    if match_facebook_story(raw, stories):
                        item["_network_url"] = network["url"]
                    item["sponsored"] |= network["sponsored"]
                    pid = network.get("_post_id") or _extract_facebook_post_id(network.get("url") or "")
                    if is_facebook_content_url(network["url"]) or (pid and skip_keys and f"id:{pid}" in skip_keys):
                        item["_skip_link_resolve"] = True
    scroll_y = page.evaluate(FB_SCROLL_POSITION_JS)
    try:
        t_res0 = time.monotonic() if getattr(stories, "track_timings", False) else 0.0
        try:
            return _resolve_facebook_items(page, items, stories if isinstance(stories, FacebookStoryCache) else None)
        finally:
            if getattr(stories, "track_timings", False):
                stories.link_resolve_s += max(0.0, time.monotonic() - t_res0)
    finally:
        page.evaluate(FB_CLEAR_MARKERS_JS)
        page.evaluate(FB_RESTORE_SCROLL_JS, scroll_y)


def _resolve_facebook_items(page: Page, items: list[dict], stories: FacebookStoryCache | None = None) -> list[dict]:
    hover_enabled = os.getenv("FEEDLENS_FB_HOVER", "1").strip() != "0"
    hover_budget = 3 if hover_enabled else 0
    deadline = time.monotonic() + 4
    jobs = []
    candidates = []
    candidate_ids = []
    for item in items:
        item["author"] = clean_facebook_author(item.get("author", ""))
        node_index = item.pop("_node_index", None)
        marker = item.pop("_node_marker", None)
        card_key = item.pop("_card_key", None)
        hover = item.pop("_hover", [])
        links = item.pop("links", [])
        item["sponsored"] = bool(item.get("sponsored") or any(facebook_ad_link(href) for href, _ in links))
        network_url = item.pop("_network_url", "")
        author_url = item.pop("_author_url", "")
        skip_resolve = bool(item.pop("_skip_link_resolve", False))
        item["url"] = network_url or facebook_dom_permalink(links, author_url)
        if node_index is None or skip_resolve or item["sponsored"] or is_facebook_content_url(item["url"]):
            continue
        key = None
        if stories is not None and card_key:
            # Virtualization can reuse a node with different post text or links.
            key = (card_key, item["author"], item["text"], tuple(map(tuple, links)), tuple(hover))
            if key in stories.hover_links:
                item["url"] = stories.hover_links[key]
                continue
            attempted_indices = stories.hover_attempts.get(key, set())
            hover = [index for index in hover if index not in attempted_indices]
            if attempted_indices and not hover:
                continue
        selector = NODE_MARKER.format(marker=marker) if str(marker).isdigit() else None
        node = page.locator(selector) if selector else page.locator(FB_NODE_SELECTOR).nth(node_index)
        jobs.append((item, node, hover, selector, key))
        if len(candidates) < 10 and not item["sponsored"] and not is_facebook_content_url(item["url"]):
            candidate_ids.append(id(item))
            candidates.append(dict(selector=selector, index=node_index, text=item["text"]))
    # Capture every candidate before any hover scrolls and virtualizes its siblings.
    snapshots = {}
    if candidates:
        try:
            captured = page.evaluate(FB_CAPTURE_SNAPSHOTS_JS, candidates)
            snapshots = dict(zip(candidate_ids, captured))
        except Exception:  # noqa: BLE001 — diagnostics must never interrupt collection
            pass
    for item, node, hover, selector, key in jobs:
        status = "no_timestamp" if hover_enabled else "hover_disabled"
        attempted = 0
        if not item["sponsored"] and not is_facebook_content_url(item["url"]):
            if hover and hover_budget > 0 and time.monotonic() < deadline:
                try:
                    node.scroll_into_view_if_needed(timeout=700)
                    if selector:
                        page.wait_for_function(FB_WAIT_FOR_STORY_JS,
                            arg={"selector": selector, "text": item["text"]}, timeout=700)
                    else:
                        page.wait_for_timeout(100)
                    refreshed = node.evaluate(FB_JS, timeout=700)
                    if refreshed and refreshed[0]["text"] == item["text"]:
                        hover = refreshed[0]["_hover"]
                        if key is not None:
                            hover = [index for index in hover if index not in stories.hover_attempts.get(key, ())]
                        item["sponsored"] |= refreshed[0]["sponsored"]
                        item["url"] = facebook_dom_permalink(refreshed[0]["links"], refreshed[0]["_author_url"])
                    else:
                        hover = []; status = "post_not_visible"
                except PlaywrightTimeoutError:
                    hover = []; status = "post_not_visible"
            for index in hover if hover_enabled and not is_facebook_content_url(item["url"]) and not item["sponsored"] else []:
                if hover_budget <= 0 or time.monotonic() >= deadline:
                    status = "budget_exhausted"; break
                anchor = node.locator(FB_LINK_SELECTOR).nth(index)
                try:
                    hover_budget -= 1; attempted += 1
                    anchor.hover(timeout=700)
                    page.wait_for_timeout(150)
                    links = node.evaluate(
                        FB_HOVER_LINKS_JS,
                        {"index": index, "text": item["text"]})
                    item["sponsored"] |= any(facebook_ad_link(href) for href, _ in links)
                    if any(timestamp and select_facebook_link([(href, True)]) for href, timestamp in links):
                        item["url"] = select_facebook_link([(item["url"], False), *links])
                        status = "resolved"; break
                    status = "hover_no_url"
                    if key is not None:
                        stories.hover_attempts.setdefault(key, set()).add(index)
                except PlaywrightTimeoutError:
                    status = "hover_timeout"
        if key is not None and status == "resolved" and is_facebook_content_url(item["url"]) and not item["sponsored"]:
            stories.hover_links[key] = item["url"]
        if not item["sponsored"] and not is_facebook_content_url(item["url"]) and id(item) in candidate_ids:
            snapshot = snapshots.pop(id(item), None)
            if snapshot is None:
                snapshot = '<section data-feedlens-snapshot="3" data-feedlens-capture="not_visible"></section>'
            trace = escape(json.dumps(dict(status=status, attempts=attempted)), quote=True)
            item["_missing_header"] = ('<section data-feedlens-snapshot="3" data-feedlens-author="' + escape(item["author"], quote=True)
                + '" data-feedlens-hover="' + trace + '"><p>' + escape(item["text"][:30]) + '</p>' + snapshot + '</section>')
    return items


FB_EXPAND_JS = load_script("feedlens.scrapers.facebook", 'expand.js', SELECTORS)


FB_EXPAND_CANDIDATES_JS = load_script("feedlens.scrapers.facebook", 'expand_candidates.js', SELECTORS)


FB_EXPAND_CLICK_JS = load_script("feedlens.scrapers.facebook", 'expand_click.js', SELECTORS)


def _wait_for_facebook_scroll(page: Page, stories: FacebookStoryCache, url: str, group: bool,
                              messages: set[str], story_keys: set[str], response_count: int,
                              pause: tuple[float, float]) -> bool:
    floor, ceiling = (round(seconds * 1000) for seconds in pause)
    deadline = time.monotonic() + ceiling / 1000
    # Playwright pumps response callbacks while waiting. Keep the existing minimum interval.
    page.wait_for_timeout(floor)
    remaining = ceiling - floor
    while True:
        if stories.response_count > response_count:
            return True
        if any(key not in story_keys and (not group or _facebook_story_belongs_to_group(story, url))
               for key, story in stories.by_id.items()):
            return True
        current = page.evaluate(FB_SCROLL_MESSAGES_JS) or []
        if any(message not in messages for message in current):
            return True
        delay = min(200, remaining, round((deadline - time.monotonic()) * 1000))
        if delay <= 0:
            return False
        page.wait_for_timeout(delay)
        remaining -= delay

FB_CAPTURE_SNAPSHOTS_JS = load_script("feedlens.scrapers.facebook", 'capture_snapshots.js', SELECTORS).replace("__SNAPSHOT__", FB_HEADER_SNAPSHOT_JS)
