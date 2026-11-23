"""Facebook DOM extraction, expansion and scroll waits."""
from __future__ import annotations

import json
import os
import time
from html import escape
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from ..models import RawPost
from .facebook_links import (
    clean_facebook_author,
    facebook_ad_link,
    facebook_dom_permalink,
    is_facebook_content_url,
    select_facebook_link,
)
from .facebook_stories import (
    FacebookStoryCache,
    _extract_facebook_post_id,
    _facebook_story_belongs_to_group,
    _match_facebook_story_by_id,
    match_facebook_story,
)


FB_NODE_SELECTOR = 'div[role="feed"] > div, [role="article"], [aria-posinset]'


FB_LINK_SELECTOR = 'a, [role="link"]'


FB_SCROLL_MESSAGES_JS = r"""
() => [...document.querySelectorAll('[data-ad-preview="message"], [data-ad-comet-preview="message"]')]
  .slice(-30).map(n => (n.textContent || '').trim().slice(0, 240)).filter(Boolean)
"""


FB_JS = r"""
(root) => {
  const out = [];
  const cards = window.__feedlensCards ||= { keys: new WeakMap(), next: 0 };
  if (!root) document.querySelectorAll('[data-feedlens-node]').forEach(n => n.removeAttribute('data-feedlens-node'));
  const nodes = root ? [root] : document.querySelectorAll('__NODES__');
  for (const [nodeIndex, n] of [...nodes].entries()) {
    // Feed wrappers and nested shared articles must not produce duplicate posts.
    const article = '[role="article"], [aria-posinset]';
    if (!root && !n.matches(article) && n.querySelector(article)) continue;
    if (!root && n.parentElement?.closest(article)) continue;
    if (!root) n.setAttribute('data-feedlens-node', String(nodeIndex));
    const msg = n.querySelector('[data-ad-preview="message"], [data-ad-comet-preview="message"]');
    let text = msg ? msg.innerText : '';
    if (!text) {
      const blocks = [...n.querySelectorAll('div[dir="auto"]')].map(d => d.innerText).filter(t => t && t.length > 20);
      text = blocks.sort((a, b) => b.length - a.length)[0] || '';
    }
    if (!text || text.length < 15) continue;
    const authorEl = n.querySelector('h2 a, h3 a, h4 a, strong a, h2, h3, h4');
    const anchors = [...n.querySelectorAll('__LINKS__')];
    const timestamp = a => {
      if (a.closest('h2, h3, h4, strong')) return false;
      if (a.querySelector('time, abbr, [data-utime]') || a.hasAttribute('data-utime') ||
          /timestamp/i.test(a.getAttribute('data-testid') || '')) return true;
      const referenced = (a.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ').trim();
      const label = (referenced || a.innerText || a.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
      return /^(?:\d+\s*(?:s|m|h|d|w|y|sec|min|hr|hrs|hours?|days?|weeks?|minutes?|秒|分钟|小时|天|周|年|giây|phút|giờ|ngày|tuần|năm)(?:\s*(?:ago|前|trước))?|just now|yesterday|vừa xong|hôm qua|刚刚|昨天)$/i.test(label) ||
        /\b(?:January|February|March|April|May|June|July|August|September|October|November|December|tháng)\b|\d{1,4}[\/-]\d{1,2}[\/-]\d{1,4}|\d+月\d+日/i.test(a.getAttribute('aria-label') || '');
    };
    const authorUrl = authorEl?.closest('a')?.getAttribute('href') || authorEl?.querySelector('a')?.getAttribute('href') || '';
    const links = anchors.flatMap(a => [...new Set(['href', 'data-href', 'data-url', 'ajaxify']
      .map(key => a.getAttribute(key)).filter(Boolean))].map(href => [href, timestamp(a)]));
    // Obfuscated timestamps fail the text test; their href is "#" or missing until hover.
    // Real feed (2026-11): the timestamp is <a aria-labelledby=… href="?__cft__…"> until hovered.
    const placeholder = h => !h || h === '#' || h.startsWith('?');
    const lazy = a => !a.closest('h2, h3, h4, strong') && placeholder(a.getAttribute('href'))
      && !a.querySelector('img, svg image') && (a.hasAttribute('aria-labelledby') || (a.innerText || '').trim().length <= 40);
    const hover = [...new Set([
      ...anchors.flatMap((a, i) => a.hasAttribute('aria-labelledby') && lazy(a) ? [i] : []),
      ...anchors.flatMap((a, i) => timestamp(a) ? [i] : []),
      ...anchors.flatMap((a, i) => lazy(a) ? [i] : [])])].slice(0, 3);
    const adWords = /^(?:sponsored|được tài trợ|赞助内容|广告)$/i;
    const sponsored = [...n.querySelectorAll('a, span')].some(el =>
      adWords.test((el.getAttribute('aria-label') || el.innerText || '').trim()))
      || anchors.some(a => /\/ads\/about|[?&]ad_id=/.test(a.getAttribute('href') || ''))
      // Real feed samples (runs 6–10): the obfuscated "Sponsored" label is a header link whose
      // only text is U+2060; organic posts put an aria-labelledby timestamp there instead.
      || anchors.some(a => !a.closest('h2, h3, h4') && (a.textContent || '').includes('⁠')
        && /^[⁠​\s]*$/.test(a.textContent || ''));
    if (!cards.keys.has(n)) cards.keys.set(n, ++cards.next);
    out.push({ author: authorEl ? authorEl.innerText.split('\n')[0] : '', text, url: '', links,
      _card_key: performance.timeOrigin + ':' + cards.keys.get(n),
      _node_index: nodeIndex, _node_marker: n.getAttribute('data-feedlens-node'), _hover: hover, _author_url: authorUrl, posted_at: '', sponsored });
  }
  return out;
}
""".replace("__NODES__", FB_NODE_SELECTOR).replace("__LINKS__", FB_LINK_SELECTOR)


FB_HEADER_SNAPSHOT_JS = r"""
(n) => {
  const keep = new Set(['href', 'data-href', 'data-url', 'ajaxify', 'role', 'aria-label', 'aria-labelledby',
    'aria-hidden', 'data-ad-preview', 'data-ad-comet-preview', 'data-testid', 'data-utime', 'dir', 'id',
    'data-post-id', 'data-story-id', 'data-video-id']);
  const clean = root => {
    root.querySelectorAll('img, svg, video, picture, style, script, input').forEach(e => e.remove());
    for (const el of [root, ...root.querySelectorAll('*')]) {
      for (const at of [...el.attributes]) {
        if (!keep.has(at.name)) { el.removeAttribute(at.name); continue; }
        if (['href','data-href','data-url','ajaxify'].includes(at.name)) {
          try {
            const u = new URL(at.value, 'https://www.facebook.com/');
            if (!['https:', 'http:'].includes(u.protocol)) { el.removeAttribute(at.name); continue; }
            for (const k of [...u.searchParams.keys()]) if (/token|cookie|auth|session|secret|credential|dtsg|^__|^(?:fbclid|eav|paipv|_rdr|lsd|jazoest|h|u)$/i.test(k)) u.searchParams.delete(k);
            u.hash = ''; el.setAttribute(at.name, u.href);
          } catch { el.removeAttribute(at.name); }
        } else if (at.value.length > 200) el.setAttribute(at.name, at.value.slice(0, 200));
      }
    }
    const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let t = walk.nextNode(); t; t = walk.nextNode()) if (t.nodeValue.length > 30) t.nodeValue = t.nodeValue.slice(0, 30) + '…';
    return root;
  };
  const result = document.createElement('section');
  result.setAttribute('data-feedlens-snapshot', '2');
  const links = document.createElement('nav'); links.setAttribute('data-feedlens-links', '');
  // Preserve late permalinks before pruning noisy/obfuscated context; never slice raw HTML.
  const anchors = [...n.querySelectorAll('a, [role="link"]')];
  anchors.sort((a,b) => Number(/pfbid|story_fbid|fbid|\/posts\/|\/permalink\//i.test(b.getAttribute('href') || '')) - Number(/pfbid|story_fbid|fbid|\/posts\/|\/permalink\//i.test(a.getAttribute('href') || '')));
  for (const a of anchors.slice(0, 100)) {
    const c = a.cloneNode(false); c.textContent = (a.innerText || a.textContent || '').slice(0, 30);
    clean(c);
    if (links.outerHTML.length + c.outerHTML.length > 24000) continue;
    links.append(c);
    for (const id of (a.getAttribute('aria-labelledby') || '').split(/\s+/)) {
      const ref = document.getElementById(id);
      if (ref && links.outerHTML.length < 23000) {
        const label = document.createElement('span'); label.id = id; label.textContent = ref.textContent.slice(0, 30); links.append(clean(label));
      }
    }
  }
  result.append(links);
  const context = clean(n.cloneNode(true));
  context.querySelectorAll('blockquote').forEach(e => { if (e.textContent.trim() === 'Facebook') e.remove(); });
  [...context.querySelectorAll('*')].slice(300).forEach(e => e.remove());
  while (context.outerHTML.length > 12000 && context.lastElementChild) context.lastElementChild.remove();
  result.append(context);
  return result.outerHTML;
}
"""


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
    scroll_y = page.evaluate("() => window.scrollY")
    try:
        t_res0 = time.monotonic() if getattr(stories, "track_timings", False) else 0.0
        try:
            return _resolve_facebook_items(page, items, stories if isinstance(stories, FacebookStoryCache) else None)
        finally:
            if getattr(stories, "track_timings", False):
                stories.link_resolve_s += max(0.0, time.monotonic() - t_res0)
    finally:
        page.evaluate("() => document.querySelectorAll('[data-feedlens-node]').forEach(n => n.removeAttribute('data-feedlens-node'))")
        page.evaluate("y => window.scrollTo(0, y)", scroll_y)


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
        selector = f'[data-feedlens-node="{marker}"]' if str(marker).isdigit() else None
        node = page.locator(selector) if selector else page.locator(FB_NODE_SELECTOR).nth(node_index)
        jobs.append((item, node, hover, selector, key))
        if len(candidates) < 10 and not item["sponsored"] and not is_facebook_content_url(item["url"]):
            candidate_ids.append(id(item))
            candidates.append(dict(selector=selector, index=node_index, text=item["text"]))
    # Capture every candidate before any hover scrolls and virtualizes its siblings.
    snapshots = {}
    if candidates:
        try:
            captured = page.evaluate("(items) => { const snapshot = (" + FB_HEADER_SNAPSHOT_JS + "); "
                "return items.map(item => { const n = item.selector ? document.querySelector(item.selector) : "
                "document.querySelectorAll('" + FB_NODE_SELECTOR + "')[item.index]; "
                "if (!n || !n.innerText.includes(item.text)) return null; return snapshot(n); }); }", candidates)
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
                        page.wait_for_function("args => document.querySelector(args.selector)?.innerText.includes(args.text)",
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
                        "(n, args) => n.innerText.includes(args.text) ? "
                        "[...n.querySelectorAll('a, [role=link]')].flatMap((a, i) => "
                        "['href', 'data-href', 'data-url', 'ajaxify'].map(k => a.getAttribute(k))"
                        ".filter(Boolean).map(h => [h, i === args.index])) : []",
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


FB_EXPAND_JS = r"""
() => {
  const labels = ['See more', 'Xem thêm'];
  let clicked = 0;
  document.querySelectorAll('div[role="button"]').forEach(b => {
    if (labels.includes((b.innerText || '').trim())) { try { b.click(); clicked++; } catch (e) {} }
  });
  return clicked;
}
"""


FB_EXPAND_CANDIDATES_JS = r"""
() => {
  const labels = ['See more', 'Xem thêm'];
  const out = [];
  document.querySelectorAll('[data-feedlens-expand]').forEach(b => b.removeAttribute('data-feedlens-expand'));
  document.querySelectorAll('div[role="button"]').forEach((b, idx) => {
    if (!labels.includes((b.innerText || '').trim())) return;
    const n = b.closest('[role="article"], [aria-posinset], div[role="feed"] > div');
    if (!n) return;
    const msg = n.querySelector('[data-ad-preview="message"], [data-ad-comet-preview="message"]');
    let text = msg ? msg.innerText : '';
    if (!text) {
      const blocks = [...n.querySelectorAll('div[dir="auto"]')].map(d => d.innerText).filter(t => t && t.length > 20);
      text = blocks.sort((a, b) => b.length - a.length)[0] || '';
    }
    const authorEl = n.querySelector('h2 a, h3 a, h4 a, strong a, h2, h3, h4');
    b.setAttribute('data-feedlens-expand', String(idx));
    const links = [...n.querySelectorAll('a[href]')]
      .filter(a => a.closest('[role="article"], [aria-posinset], div[role="feed"] > div') === n)
      .map(a => a.getAttribute('href'));
    out.push({ idx, author: authorEl ? authorEl.innerText.split('\n')[0] : '', text, links });
  });
  return out;
}
"""


FB_EXPAND_CLICK_JS = r"""
(indices) => {
  const wanted = new Set(indices || []);
  let clicked = 0;
  document.querySelectorAll('[data-feedlens-expand]').forEach(b => {
    const id = Number(b.getAttribute('data-feedlens-expand'));
    b.removeAttribute('data-feedlens-expand');
    if (wanted.has(id)) { try { b.click(); clicked++; } catch (e) {} }
  });
  return clicked;
}
"""


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
