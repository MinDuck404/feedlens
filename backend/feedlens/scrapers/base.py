"""Shared collection loop, pacing and verification."""
from __future__ import annotations

from feedlens.scrapers.selectors import PASSWORD_INPUT
from feedlens.scrapers.scripts import load_script
from feedlens.scrapers.facebook.selectors import SELECTORS

FB_INITIAL_STORIES_JS = load_script("feedlens.scrapers.facebook", 'initial_stories.js', SELECTORS)

import feedlens.scrapers.facebook.dom as facebook_dom

import random
import re
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import parse_qsl, urlsplit
from playwright.sync_api import Page

from ..models import RawPost
from feedlens.scrapers.facebook.links import POST_LINK_RE
from feedlens.scrapers.facebook.links import clean_facebook_author
from feedlens.scrapers.facebook.links import facebook_ad_link
from feedlens.scrapers.facebook.links import is_facebook_content_url
from feedlens.scrapers.facebook.links import select_facebook_link
from feedlens.scrapers.facebook.stories import FacebookStoryCache
from feedlens.scrapers.facebook.stories import _extract_facebook_post_id
from feedlens.scrapers.facebook.stories import _facebook_story_belongs_to_group
from feedlens.scrapers.facebook.stories import _should_use_story_text
from feedlens.scrapers.facebook.stories import cache_facebook_stories
from feedlens.scrapers.facebook.stories import capture_facebook_response
from feedlens.scrapers.facebook.stories import facebook_graphql_debug
from feedlens.scrapers.facebook.stories import match_facebook_story
from feedlens.scrapers.facebook.dom import FB_EXPAND_CANDIDATES_JS
from feedlens.scrapers.facebook.dom import FB_EXPAND_CLICK_JS
from feedlens.scrapers.facebook.dom import FB_SCROLL_MESSAGES_JS
from feedlens.scrapers.facebook.dom import _wait_for_facebook_scroll


ProgressFn = Callable[[int, str], None]


def is_chronological_url(url: str) -> bool:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    if parts.path in ("", "/"):
        return False  # Home feeds are ranked, even if an unrelated sort flag exists.
    return (query.get("sorting_setting", "").upper() == "CHRONOLOGICAL"
            or bool(re.fullmatch(r"/r/[^/]+/new/?", parts.path))
            or query.get("sort", "").strip('"').lower() in {"new", "latest", "date_posted"}
            or query.get("f") == "live")


STOP_REASON_TEXT = {
    "target_reached": "đủ số bài",
    "caught_up": "đã gặp toàn bài cũ, coi như hết bài mới",
    "budget_exhausted": "hết giới hạn thời gian/số bài được duyệt",
    "no_more_posts": "trang không tải thêm bài",
    "interrupted": "bị gián đoạn",
}


def collection_message(report: dict) -> str:
    reason = STOP_REASON_TEXT.get(report.get("stop_reason") or "", "")
    return (f"Lấy được {report['collected']}/{report['target']} bài mới · bỏ qua {report['skipped_old']} bài đã có"
            + (f" · bỏ qua {report.get('skipped_ads', 0)} quảng cáo" if report.get("skipped_ads") else "")
            + (f" · dừng vì {reason}" if reason else ""))


@dataclass
class Scraper:
    platform: str
    extract_js: str
    expand_js: str | None = None

    def urls(self, source_type: str, sources: list[str]) -> list[tuple[str, str]]:
        """Trả về [(label, url)] cần lướt."""
        raise NotImplementedError

    def extract_items(self, page: Page, stories: dict) -> list[dict]:
        if self.platform == "facebook":
            return facebook_dom._facebook_items(page, stories)
        return page.evaluate(self.extract_js)

    def scroll(self, page: Page, distance: int) -> None:
        page.mouse.wheel(0, distance)

    def next_page(self, url: str) -> str | None:
        return None

    def _expand(self, page: Page, stories: dict, url: str, label: str) -> int:
        if not self.expand_js:
            return 0
        skip_keys = getattr(stories, "skip_keys", None) if stories is not None else None
        if self.platform == "facebook" and (stories or skip_keys):
            candidates = page.evaluate(FB_EXPAND_CANDIDATES_JS) or []
            if not candidates:
                return 0
            click_ids = []
            for cand in candidates:
                text = cand.get("text") or ""
                author = clean_facebook_author(cand.get("author") or "")
                candidates_by_id = {}
                for href in cand.get("links", []):
                    if POST_LINK_RE.search(href) and (link := select_facebook_link([(href, False)])):
                        if pid := _extract_facebook_post_id(link):
                            candidates_by_id[pid] = link
                probe_url = next(iter(candidates_by_id.values())) if len(candidates_by_id) == 1 else ""
                pid = _extract_facebook_post_id(probe_url)
                if pid and skip_keys and f"id:{pid}" in skip_keys:
                    continue
                probe = RawPost(platform="facebook", source=label, author=author, text=text, url=probe_url)
                if skip_keys and f"fp:{probe.fingerprint}" in skip_keys:
                    continue
                network = match_facebook_story(probe, stories) if stories else None
                if network:
                    pid = network.get("_post_id") or _extract_facebook_post_id(network.get("url") or "")
                    if (pid and skip_keys and f"id:{pid}" in skip_keys) or _should_use_story_text(text, network, url):
                        continue
                click_ids.append(cand["idx"])
            return int(page.evaluate(FB_EXPAND_CLICK_JS, click_ids) or 0)
        return int(page.evaluate(self.expand_js) or 0)

    # -- vòng lặp cuộn chung --
    def collect(self, page: Page, url: str, label: str, target: int,
                seen: set[str], progress: ProgressFn, speed: str = "fast", interactive: bool = True,
                chronological: bool | None = None, leading_old_grace: int = 0,
                report: dict | None = None, old_streak_limit: int = 8,
                history: frozenset[str] | None = None) -> list[RawPost]:
        pace = PACE.get(speed, PACE["fast"])
        posts: list[RawPost] = []
        collected: dict[str, RawPost] = {}
        encountered: set[str] = set()
        prior = frozenset(seen) if history is None else history
        earlier_sources = seen.difference(prior)
        stale_rounds = consecutive_old = 0
        # Scale with the quota so large runs are not cut short; old-post streaks still end within minutes.
        deadline = time.monotonic() + (max(300, 8 * target) if speed == "careful" else max(180, 4 * target))
        max_examined = max(20, 4 * target)
        chronological = is_chronological_url(url) if chronological is None else chronological
        leading_old = 0
        leading = True
        page_start = empty_pages = 0
        self.last_report = dict(target=target, collected=0, skipped_old=0, skipped_dup=0,
                                skipped_ads=0, examined=0, stop_reason=None)
        self.missing_headers: list[str] = []
        self.missing_graphql_samples: list[dict] = []
        timings: dict[str, float] | None = None
        if report is not None:
            timings = report.setdefault("timings", {})
            for key in ("navigation", "scroll_wait", "scroll_ready_wait", "scroll_timeout_wait", "expand", "link_resolve", "extract"):
                timings[key] = float(timings.get(key, 0.0))
            report["full_text_from_story"] = int(report.get("full_text_from_story", 0))
            report["from_story"] = int(report.get("from_story", 0))
        is_group_mode = (self.platform == "facebook" and bool(re.fullmatch(r"/groups/([\w.-]+)/?", urlsplit(url).path)))
        consumed_story_keys: set[str] = set()
        collected_post_ids: set[str] = set()
        debug_posts: dict[str, RawPost] = {}
        reason = None
        stories = FacebookStoryCache()
        stories.track_timings = timings is not None
        stories.skip_keys = encountered

        def record_post(p: RawPost, post_id: str = "", *, from_story: bool = False,
                        replaced_full_text: bool = False, header: str = "") -> None:
            nonlocal leading, leading_old, consecutive_old, reason
            fp = p.fingerprint
            dedup_key = f"id:{post_id}" if post_id else f"fp:{fp}"
            if post_id and post_id in collected_post_ids:
                return
            if dedup_key in encountered:
                return
            encountered.add(dedup_key)
            if post_id:
                collected_post_ids.add(post_id)
            if replaced_full_text and report is not None:
                report["full_text_from_story"] += 1
            if header and not p.sponsored and not facebook_ad_link(p.url) and len(self.missing_headers) < 10:
                self.missing_headers.append(header)
            if self.platform == "facebook" and (p.sponsored or facebook_ad_link(p.url)):
                self.last_report["skipped_ads"] += 1
                # Ads do not count as old-post streaks and never enter seen/history.
            elif fp in prior:
                self.last_report["skipped_old"] += 1
                if leading and leading_old < leading_old_grace:
                    leading_old += 1
                else:
                    consecutive_old += 1
            elif fp in earlier_sources or (not post_id and fp in seen):
                self.last_report["skipped_dup"] += 1
            else:
                leading = False
                consecutive_old = 0
                seen.add(fp)
                collected[dedup_key] = p
                posts.append(p)
                if from_story and report is not None:
                    report["from_story"] += 1
            self.last_report.update(collected=len(posts), examined=len(encountered))
            if len(posts) >= target:
                reason = "target_reached"
            elif chronological and consecutive_old >= old_streak_limit:
                reason = "caught_up"
            elif len(encountered) >= max_examined or time.monotonic() >= deadline:
                reason = "budget_exhausted"
        listening = self.platform == "facebook" and hasattr(page, "on")
        def on_response(response):
            capture_facebook_response(response, stories, url)
        if listening:
            page.on("response", on_response)
        try:
            t_nav0 = time.monotonic() if timings is not None else 0.0
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                self.ensure_access(page, url, progress, interactive)
                _human_pause(*pace["settle"])
            finally:
                if timings is not None:
                    timings["navigation"] += max(0.0, time.monotonic() - t_nav0)
            if listening:
                for body in page.evaluate(FB_INITIAL_STORIES_JS):
                    cache_facebook_stories(body, stories, url)
            while reason is None:
                if time.monotonic() >= deadline:
                    reason = "budget_exhausted"; break
                if self.ensure_access(page, url, progress, interactive):
                    stale_rounds = 0
                before = len(encountered)
                if is_group_mode and stories.by_id:
                    pending_stories = [
                        (skey, s) for skey, s in stories.by_id.items()
                        if skey not in consumed_story_keys and _facebook_story_belongs_to_group(s, url)
                    ]
                    pending_stories.sort(key=lambda pair: -int(pair[1].get("_creation_time") or 0))
                    for skey, s in pending_stories:
                        consumed_story_keys.add(skey)
                        spid = s.get("_post_id") or _extract_facebook_post_id(s.get("url", ""))
                        sp = RawPost(
                            platform="facebook", source=label,
                            author=s["author"], text=s["text"], url=s["url"],
                            posted_at=s["posted_at"], sponsored=s["sponsored"],
                        )
                        record_post(sp, spid, from_story=True)
                        if reason is not None:
                            break
                if reason is not None:
                    self.last_report["stop_reason"] = reason
                    progress(len(posts), collection_message(self.last_report))
                    break
                t_exp0 = time.monotonic() if timings is not None else 0.0
                if self._expand(page, stories, url, label) > 0:
                    _human_pause(*pace["expand"])
                if timings is not None:
                    timings["expand"] += max(0.0, time.monotonic() - t_exp0)
                prev_lr = stories.link_resolve_s
                t_ext0 = time.monotonic() if timings is not None else 0.0
                items = self.extract_items(page, stories)
                if timings is not None:
                    ext_dt = max(0.0, time.monotonic() - t_ext0)
                    lr_dt = max(0.0, stories.link_resolve_s - prev_lr)
                    timings["link_resolve"] += lr_dt
                    timings["extract"] += max(0.0, ext_dt - lr_dt)
                for item in items:
                    header = item.pop("_missing_header", "")
                    p = RawPost(platform=self.platform, source=label, **item)
                    replaced_full_text = False
                    network = match_facebook_story(p, stories) if self.platform == "facebook" else None
                    if network:
                        p.sponsored |= network["sponsored"]
                        if network["url"]:
                            p.url = network["url"]
                            header = ""  # Network enrichment resolved the missing DOM permalink.
                        if not p.posted_at:
                            p.posted_at = network["posted_at"]
                        if _should_use_story_text(p.text, network, url):
                            p.text = network["text"]
                            replaced_full_text = True
                    post_id = ((network.get("_post_id") if network else "") or _extract_facebook_post_id(p.url)) if self.platform == "facebook" else ""
                    fp = p.fingerprint
                    dedup_key = f"id:{post_id}" if post_id else f"fp:{fp}"
                    if dedup_key in collected and not collected[dedup_key].url and p.url:
                        collected[dedup_key].url = p.url
                    if self.platform == "facebook":
                        if p.sponsored or is_facebook_content_url(p.url):
                            debug_posts.pop(fp, None)
                        elif fp in debug_posts or len(debug_posts) < 10:
                            debug_posts[fp] = p
                    record_post(p, post_id, replaced_full_text=replaced_full_text, header=header)
                    if reason is not None:
                        break
                stale_rounds = stale_rounds + 1 if len(encountered) == before else 0
                moved_page = False
                if stale_rounds >= pace["stale"]:
                    next_url = self.next_page(url) if reason is None else None
                    empty_pages = empty_pages + 1 if len(encountered) == page_start else 0
                    if next_url and empty_pages < 2:
                        url = next_url
                        t_nav1 = time.monotonic() if timings is not None else 0.0
                        try:
                            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                            self.ensure_access(page, url, progress, interactive)
                            _human_pause(*pace["settle"])
                        finally:
                            if timings is not None:
                                timings["navigation"] += max(0.0, time.monotonic() - t_nav1)
                        page_start = len(encountered)
                        stale_rounds = 0
                        moved_page = True
                    elif reason is None:
                        reason = "no_more_posts"
                self.last_report["stop_reason"] = reason
                progress(len(posts), collection_message(self.last_report))
                if reason:
                    break
                if moved_page:
                    continue  # Read the top cards before scrolling a newly loaded page.
                wait_for_signal = self.platform == "facebook" and hasattr(page, "wait_for_timeout")
                t_scr0 = time.monotonic() if timings is not None else 0.0
                if wait_for_signal:
                    messages = set(page.evaluate(FB_SCROLL_MESSAGES_JS) or [])
                    story_keys = set(stories.by_id)
                    response_count = stories.response_count
                self.scroll(page, random.randint(*pace["scroll"]))
                if wait_for_signal:
                    wait_start = time.monotonic()
                    ready = _wait_for_facebook_scroll(page, stories, url, is_group_mode, messages, story_keys,
                                                      response_count, pace["pause"])
                    if timings is not None:
                        bucket = "scroll_ready_wait" if ready else "scroll_timeout_wait"
                        timings[bucket] = timings.get(bucket, 0.0) + max(0.0, time.monotonic() - wait_start)
                else:
                    _human_pause(*pace["pause"])
                if random.random() < pace["long_chance"]:
                    _human_pause(*pace["long"])
                if timings is not None:
                    timings["scroll_wait"] += max(0.0, time.monotonic() - t_scr0)
        finally:
            if listening:
                page.remove_listener("response", on_response)
            # Responses can arrive after a post was first seen; diagnose the final cache state.
            for fp, post in debug_posts.items():
                latest = match_facebook_story(post, stories)
                if latest and (latest["sponsored"] or is_facebook_content_url(latest["url"])):
                    target_post = collected.get(f"fp:{fp}")
                    if target_post is not None and not latest["sponsored"] and latest["url"] and not target_post.url:
                        target_post.url = latest["url"]
                    continue
                self.missing_graphql_samples.append(facebook_graphql_debug(post, stories))
            self.last_report.update(collected=len(posts), stop_reason=reason or "interrupted")
            progress(len(posts), collection_message(self.last_report))
        return posts

    def blocked(self, url: str) -> bool:
        return is_blocked_url(self.platform, url)

    def blocked_page(self, page: Page) -> bool:
        """Bị đòi đăng nhập/xác minh: URL checkpoint, hoặc trang hiện form đăng nhập
        (Facebook hiện form ngay tại facebook.com/ khi cookie hỏng, URL không đổi)."""
        return self.blocked(page.url) or has_login_form(page)

    def ensure_access(self, page: Page, url: str, progress: ProgressFn, interactive: bool) -> bool:
        """Nếu nền tảng chuyển sang trang đăng nhập / xác minh 2 bước / checkpoint:
        - có cửa sổ: chờ người dùng tự xác minh (không tự giải CAPTCHA), rồi mở lại trang cần lướt;
        - chạy ẩn: báo lỗi rõ ràng thay vì lướt ra 0 bài.
        Trả về True nếu đã phải chờ và mở lại trang."""
        if not self.blocked_page(page):
            return False
        if not interactive:
            raise NeedsVerification(
                f"{self.platform} đang yêu cầu đăng nhập hoặc xác minh. Tắt chế độ chạy ẩn để xác minh "
                f"trong cửa sổ Chrome, hoặc chạy `feedlens login {self.platform}`.")
        deadline = time.time() + VERIFY_TIMEOUT
        while self.blocked_page(page):
            left = int(deadline - time.time())
            if left <= 0:
                raise NeedsVerification(f"Hết {VERIFY_TIMEOUT // 60} phút chờ xác minh {self.platform}. Hãy chạy lại.")
            progress(0, f"{self.platform} yêu cầu xác minh (2 bước / CAPTCHA). Hãy hoàn tất trong cửa sổ Chrome, "
                        f"bot sẽ tự lướt tiếp (còn {left // 60}:{left % 60:02d}).")
            page.wait_for_timeout(2000)  # page.is_closed() / lỗi Target closed nếu người dùng đóng cửa sổ
        page.wait_for_timeout(1500)
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        return True


class NeedsVerification(RuntimeError):
    pass


VERIFY_TIMEOUT = 600


BLOCKED_PATHS: dict[str, tuple[str, ...]] = {
    "facebook": ("/checkpoint", "two_step_verification", "/login", "/recover", "/two_factor"),
    "linkedin": ("/checkpoint", "/login", "/authwall", "/uas/login"),
    "x": ("/i/flow/login", "/account/access", "/i/flow/two-factor"),
    "reddit": ("/login", "/account/login"),
}


def is_blocked_url(platform: str, url: str) -> bool:
    return any(p in url for p in BLOCKED_PATHS.get(platform, ()))


def has_login_form(page) -> bool:
    """Trang đang hiện ô nhập mật khẩu = chưa đăng nhập (dù URL trông bình thường)."""
    try:
        return page.locator(PASSWORD_INPUT).count() > 0
    except Exception:  # noqa: BLE001 — trang đang chuyển hoặc đối tượng giả trong test
        return False


PACE: dict[str, dict] = {
    "fast": {"settle": (1.5, 2.5), "expand": (0.2, 0.5), "scroll": (1800, 2800), "pause": (0.8, 1.6),
             "long_chance": 0.04, "long": (2, 4), "stale": 5},
    "careful": {"settle": (3, 5), "expand": (0.6, 1.2), "scroll": (900, 1700), "pause": (1.8, 4.2),
                "long_chance": 0.12, "long": (5, 9), "stale": 6},
}


def _human_pause(lo: float, hi: float) -> None:
    time.sleep(random.uniform(lo, hi))
