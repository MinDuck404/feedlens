"""Bộ lướt cho từng nền tảng.

Mỗi nền tảng khai báo: URL cần mở theo loại nguồn (feed/group/search) và một đoạn JS
trích xuất bài viết đang hiển thị. Vòng lặp cuộn chung xử lý nhịp độ giống người,
khử trùng lặp và dừng khi đủ số bài hoặc hết nội dung mới.

Selector của mạng xã hội thay đổi thường xuyên — khi một nền tảng ngừng trả bài,
hãy sửa đoạn JS tương ứng trong file này.
"""
from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlsplit, urlunsplit

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from .models import RawPost

ProgressFn = Callable[[int, str], None]


def select_facebook_link(links: list[tuple[str, bool]]) -> str:
    """Prefer post permalinks, then timestamp anchors, then media fallbacks."""
    best_url, best_rank = "", (3, True)
    for href, timestamp in links:
        if not href or href.startswith("#"):
            continue
        try:
            url = urlsplit(urljoin("https://www.facebook.com/", href))
        except ValueError:
            continue
        host = (url.hostname or "").lower()
        if url.scheme not in ("http", "https") or not (host == "facebook.com" or host.endswith(".facebook.com") or host == "fb.watch"):
            continue
        if url.path in ("", "/"):
            continue
        query = [(k, v) for k, v in parse_qsl(url.query, keep_blank_values=True)
                 if not k.startswith(("__cft__", "__tn__")) and k != "fbclid"]
        post = bool(re.search(r"/(?:posts|permalink)/[^/]+|^/share/(?:[prv]/)?[^/]+", url.path)) or any(k == "story_fbid" and v for k, v in query)
        media = bool(re.search(r"/(?:photos?|videos?|reels?)(?:/|\.php$)|^/watch/?$", url.path)) or host == "fb.watch"
        rank = (0 if post else 1 if timestamp else 2 if media else 3, not timestamp)
        if rank < best_rank:
            best_url = urlunsplit((url.scheme, url.netloc, url.path, urlencode(query), url.fragment))
            best_rank = rank
    return best_url

# --- JS extractors: trả về [{author, text, url, posted_at}] ---------------------------

FB_NODE_SELECTOR = 'div[role="feed"] > div, [role="article"], [aria-posinset]'
FB_LINK_SELECTOR = 'a, [role="link"]'

FB_JS = r"""
() => {
  const out = [];
  const nodes = document.querySelectorAll('__NODES__');
  for (const [nodeIndex, n] of [...nodes].entries()) {
    // Feed wrappers and nested shared articles must not produce duplicate posts.
    const article = '[role="article"], [aria-posinset]';
    if (!n.matches(article) && n.querySelector(article)) continue;
    if (n.parentElement?.closest(article)) continue;
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
      const label = (a.innerText || a.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
      return /^(?:\d+\s*(?:s|m|h|d|w|y|sec|min|hr|hrs|hours?|days?|weeks?|minutes?|秒|分钟|小时|天|周|年|giây|phút|giờ|ngày|tuần|năm)(?:\s*(?:ago|前))?|just now|yesterday|vừa xong|hôm qua|刚刚|昨天)$/i.test(label) ||
        /\b(?:January|February|March|April|May|June|July|August|September|October|November|December|tháng)\b|\d{1,4}[\/-]\d{1,2}[\/-]\d{1,4}|\d+月\d+日/i.test(a.getAttribute('aria-label') || '');
    };
    const links = anchors.flatMap(a => [...new Set(['href', 'data-href', 'data-url', 'ajaxify']
      .map(key => a.getAttribute(key)).filter(Boolean))].map(href => [href, timestamp(a)]));
    // Obfuscated timestamps fail the text test; their href is "#" or missing until hover.
    // Real feed (2026-11): the timestamp is <a aria-labelledby=… href="?__cft__…"> until hovered.
    const placeholder = h => !h || h === '#' || h.startsWith('?');
    const lazy = a => !a.closest('h2, h3, h4, strong') && placeholder(a.getAttribute('href'))
      && !a.querySelector('img, svg image') && (a.innerText || '').trim().length <= 40;
    const hover = [...new Set([
      ...anchors.flatMap((a, i) => a.hasAttribute('aria-labelledby') && lazy(a) ? [i] : []),
      ...anchors.flatMap((a, i) => timestamp(a) ? [i] : []),
      ...anchors.flatMap((a, i) => lazy(a) ? [i] : [])])].slice(0, 3);
    const adWords = /^(?:sponsored|được tài trợ|赞助内容|广告)$/i;
    const sponsored = [...n.querySelectorAll('a, span')].slice(0, 60).some(el =>
      adWords.test((el.getAttribute('aria-label') || el.innerText || '').trim()))
      || anchors.some(a => /\/ads\/about|[?&]ad_id=/.test(a.getAttribute('href') || ''));
    out.push({ author: authorEl ? authorEl.innerText.split('\n')[0] : '', text, url: '', links,
      _node_index: nodeIndex, _hover: hover, posted_at: '', sponsored });
  }
  return out;
}
""".replace("__NODES__", FB_NODE_SELECTOR).replace("__LINKS__", FB_LINK_SELECTOR)


POST_LINK_RE = re.compile(r"/(?:posts|permalink)/|story_fbid=|^https?://[^/]+/share/")

# Shrunk outerHTML of a post whose permalink was not found: structure only, short text, no tokens.
FB_HEADER_SNAPSHOT_JS = r"""
(n) => {
  const c = n.cloneNode(true);
  c.querySelectorAll('img, svg, video, picture, style, script').forEach(e => e.remove());
  const keep = new Set(['href', 'role', 'aria-label', 'aria-labelledby', 'aria-hidden', 'data-ad-preview',
                        'data-ad-comet-preview', 'data-testid', 'data-utime', 'dir', 'id']);
  for (const el of [c, ...c.querySelectorAll('*')]) {
    for (const at of [...el.attributes]) if (!keep.has(at.name)) el.removeAttribute(at.name);
    const href = el.getAttribute('href');
    if (href) el.setAttribute('href', href.replace(/([?&])(?:__cft__|__tn__|fbclid|eav|paipv|_rdr)[^&]*/g, '$1'));
  }
  const walk = document.createTreeWalker(c, NodeFilter.SHOW_TEXT);
  for (let t = walk.nextNode(); t; t = walk.nextNode()) if (t.nodeValue.length > 30) t.nodeValue = t.nodeValue.slice(0, 30) + '…';
  return c.outerHTML.slice(0, 12000);
}
"""


def _facebook_items(page: Page) -> list[dict]:
    items = page.evaluate(FB_JS)
    # Hovering scrolls each anchor into view; without restoring, the feed never advances.
    scroll_y = page.evaluate("() => window.scrollY")
    try:
        return _resolve_facebook_items(page, items)
    finally:
        page.evaluate("y => window.scrollTo(0, y)", scroll_y)


def _resolve_facebook_items(page: Page, items: list[dict]) -> list[dict]:
    # Bound extra work on long feeds; never click or open the post.
    hover_budget = 6
    snapshots = 3
    deadline = time.monotonic() + 4
    for item in items:
        node_index = item.pop("_node_index", None)
        hover = item.pop("_hover", [])
        item["url"] = select_facebook_link(item.pop("links", []))
        if node_index is None:
            continue
        node = page.locator(FB_NODE_SELECTOR).nth(node_index)
        for index in hover if not POST_LINK_RE.search(item["url"]) else []:
            if hover_budget <= 0 or time.monotonic() >= deadline:
                break
            anchor = node.locator(FB_LINK_SELECTOR).nth(index)
            try:
                href = anchor.get_attribute("href", timeout=700) or ""
                # The outer post's known timestamp takes precedence over shared posts.
                if re.search(r"/(?:posts|permalink)/|story_fbid=|^https?://[^/]+/share/|^/share/", href):
                    break
                hover_budget -= 1
                anchor.hover(timeout=700)
                page.wait_for_timeout(150)
                links = node.evaluate(
                    "(n, args) => n.innerText.includes(args.text) ? "
                    "[...n.querySelectorAll('a, [role=link]')].flatMap((a, i) => "
                    "['href', 'data-href', 'data-url', 'ajaxify'].map(k => a.getAttribute(k))"
                    ".filter(Boolean).map(h => [h, i === args.index])) : []",
                    {"index": index, "text": item["text"]})
                # The feed can recycle this DOM node while hovering.
                if any(timestamp and select_facebook_link([(href, True)]) for href, timestamp in links):
                    item["url"] = select_facebook_link([(item["url"], False), *links])
                    break
            except PlaywrightTimeoutError:
                continue  # Virtualized/hidden timestamp: retain the best static link.
        if snapshots and not POST_LINK_RE.search(item["url"]):
            snapshots -= 1
            try:
                item["_missing_header"] = node.evaluate(FB_HEADER_SNAPSHOT_JS, timeout=700)
            except Exception:  # noqa: BLE001 — diagnostics must never break a run
                pass
    return items


FB_EXPAND_JS = r"""
() => {
  const labels = ['See more', 'Xem thêm'];
  document.querySelectorAll('div[role="button"]').forEach(b => {
    if (labels.includes((b.innerText || '').trim())) { try { b.click(); } catch (e) {} }
  });
}
"""

LINKEDIN_JS = r"""
() => [...document.querySelectorAll('div.feed-shared-update-v2, div[data-urn^="urn:li:activity"]')].map(n => {
  const t = n.querySelector('.update-components-text, .feed-shared-update-v2__description');
  const a = n.querySelector('.update-components-actor__title span[aria-hidden="true"], .update-components-actor__name');
  const urn = n.getAttribute('data-urn') || (n.closest('[data-urn]') || {getAttribute: () => ''}).getAttribute('data-urn');
  return { author: a ? a.innerText.trim() : '', text: t ? t.innerText.trim() : '',
           url: urn ? 'https://www.linkedin.com/feed/update/' + urn + '/' : '', posted_at: '' };
}).filter(p => p.text.length > 15)
"""

LINKEDIN_EXPAND_JS = r"""
() => document.querySelectorAll('button.feed-shared-inline-show-more-text__see-more-less-toggle, .see-more').forEach(b => { try { b.click(); } catch (e) {} })
"""

X_JS = r"""
() => [...document.querySelectorAll('article[data-testid="tweet"]')].map(n => {
  const t = n.querySelector('[data-testid="tweetText"]');
  const u = n.querySelector('[data-testid="User-Name"]');
  const time = n.querySelector('time');
  const link = time && time.closest('a') ? time.closest('a').href : '';
  return { author: u ? u.innerText.split('\n').slice(0, 2).join(' ') : '', text: t ? t.innerText : '',
           url: link, posted_at: time ? time.getAttribute('datetime') : '' };
}).filter(p => p.text.length > 5)
"""

REDDIT_JS = r"""
() => [...document.querySelectorAll('shreddit-post')].map(n => {
  const body = n.querySelector('[slot="text-body"]');
  const title = n.getAttribute('post-title') || '';
  return { author: n.getAttribute('author') || '', text: (title + '\n' + (body ? body.innerText : '')).trim(),
           url: 'https://www.reddit.com' + (n.getAttribute('permalink') || ''),
           posted_at: n.getAttribute('created-timestamp') || '' };
}).filter(p => p.text.length > 5)
"""


def is_chronological_url(url: str) -> bool:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    if parts.path in ("", "/"):
        return False  # Home feeds are ranked, even if an unrelated sort flag exists.
    return (query.get("sorting_setting", "").upper() == "CHRONOLOGICAL"
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
            + (f" · dừng vì {reason}" if reason else ""))


@dataclass
class Scraper:
    platform: str
    extract_js: str
    expand_js: str | None = None

    def urls(self, source_type: str, sources: list[str]) -> list[tuple[str, str]]:
        """Trả về [(label, url)] cần lướt."""
        raise NotImplementedError

    # -- vòng lặp cuộn chung --
    def collect(self, page: Page, url: str, label: str, target: int,
                seen: set[str], progress: ProgressFn, speed: str = "fast", interactive: bool = True) -> list[RawPost]:
        pace = PACE.get(speed, PACE["fast"])
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        self.ensure_access(page, url, progress, interactive)
        _human_pause(*pace["settle"])
        posts: list[RawPost] = []
        collected: dict[str, RawPost] = {}
        encountered: set[str] = set()
        prior = set(seen)
        stale_rounds = consecutive_old = 0
        # Scale with the quota so large runs are not cut short; old-post streaks still end within minutes.
        deadline = time.monotonic() + (max(300, 8 * target) if speed == "careful" else max(180, 4 * target))
        max_examined = max(20, 4 * target)
        chronological = is_chronological_url(url)
        self.last_report = dict(target=target, collected=0, skipped_old=0, examined=0, stop_reason=None)
        self.missing_headers: list[str] = []
        reason = None
        try:
            while reason is None:
                if time.monotonic() >= deadline:
                    reason = "budget_exhausted"; break
                if self.ensure_access(page, url, progress, interactive):
                    stale_rounds = 0
                if self.expand_js:
                    page.evaluate(self.expand_js)
                    _human_pause(*pace["expand"])
                before = len(encountered)
                items = _facebook_items(page) if self.platform == "facebook" else page.evaluate(self.extract_js)
                for item in items:
                    header = item.pop("_missing_header", "")
                    p = RawPost(platform=self.platform, source=label, **item)
                    fp = p.fingerprint
                    if fp in collected and not collected[fp].url and p.url:
                        collected[fp].url = p.url
                    if fp in encountered:
                        continue
                    encountered.add(fp)
                    if header and len(self.missing_headers) < 10:
                        self.missing_headers.append(header)
                    if fp in seen:
                        if fp in prior:
                            self.last_report["skipped_old"] += 1
                            consecutive_old += 1
                    else:
                        consecutive_old = 0
                        seen.add(fp)
                        collected[fp] = p
                        posts.append(p)
                    self.last_report.update(collected=len(posts), examined=len(encountered))
                    if len(posts) >= target:
                        reason = "target_reached"; break
                    if chronological and consecutive_old >= 8:
                        reason = "caught_up"; break
                    if len(encountered) >= max_examined or time.monotonic() >= deadline:
                        reason = "budget_exhausted"; break
                stale_rounds = stale_rounds + 1 if len(encountered) == before else 0
                if stale_rounds >= pace["stale"]:
                    reason = "no_more_posts"
                self.last_report["stop_reason"] = reason
                progress(len(posts), collection_message(self.last_report))
                if reason:
                    break
                page.mouse.wheel(0, random.randint(*pace["scroll"]))
                _human_pause(*pace["pause"])
                if random.random() < pace["long_chance"]:
                    _human_pause(*pace["long"])
        finally:
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

# Đường dẫn cho thấy nền tảng đang chặn để đăng nhập / xác minh
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
        return page.locator("input[type=password]:visible").count() > 0
    except Exception:  # noqa: BLE001 — trang đang chuyển hoặc đối tượng giả trong test
        return False


# Nhịp lướt. "fast": mặc định, đủ nhanh mà vẫn có quãng nghỉ; "careful": chậm hơn, ít bị nghi ngờ hơn.
PACE: dict[str, dict] = {
    "fast": {"settle": (1.5, 2.5), "expand": (0.2, 0.5), "scroll": (1800, 2800), "pause": (0.8, 1.6),
             "long_chance": 0.04, "long": (2, 4), "stale": 5},
    "careful": {"settle": (3, 5), "expand": (0.6, 1.2), "scroll": (900, 1700), "pause": (1.8, 4.2),
                "long_chance": 0.12, "long": (5, 9), "stale": 6},
}


def _human_pause(lo: float, hi: float) -> None:
    time.sleep(random.uniform(lo, hi))


def _group_url(src: str) -> str:
    src = src.strip()
    return src if src.startswith("http") else f"https://www.facebook.com/groups/{src}"


class FacebookScraper(Scraper):
    def __init__(self):
        super().__init__("facebook", FB_JS, FB_EXPAND_JS)

    def urls(self, source_type, sources):
        if source_type == "feed" or not sources:
            return [("Bảng tin Facebook", "https://www.facebook.com/")]
        if source_type == "group":
            return [(s, _group_url(s)) for s in sources]
        # search: "group_url_or_id | từ khóa" hoặc chỉ từ khóa (tìm bài viết toàn FB)
        out = []
        for s in sources:
            if "|" in s:
                g, q = (x.strip() for x in s.split("|", 1))
                out.append((f"{g} · {q}", f"{_group_url(g).rstrip('/')}/search/?q={quote_plus(q)}"))
            else:
                out.append((f"Tìm: {s}", f"https://www.facebook.com/search/posts/?q={quote_plus(s)}"))
        return out


class LinkedInScraper(Scraper):
    def __init__(self):
        super().__init__("linkedin", LINKEDIN_JS, LINKEDIN_EXPAND_JS)

    def urls(self, source_type, sources):
        if source_type == "search" and sources:
            return [(f"Tìm: {s}", "https://www.linkedin.com/search/results/content/?keywords="
                     + quote_plus(s) + "&sortBy=%22date_posted%22") for s in sources]
        if source_type == "group" and sources:
            return [(s, s if s.startswith("http") else f"https://www.linkedin.com/groups/{s}/") for s in sources]
        return [("Bảng tin LinkedIn", "https://www.linkedin.com/feed/")]


class XScraper(Scraper):
    def __init__(self):
        super().__init__("x", X_JS)

    def urls(self, source_type, sources):
        if source_type == "search" and sources:
            return [(f"Tìm: {s}", f"https://x.com/search?q={quote_plus(s)}&f=live") for s in sources]
        if source_type == "group" and sources:  # list hoặc community URL / @user
            return [(s, s if s.startswith("http") else f"https://x.com/{s.lstrip('@')}") for s in sources]
        return [("Bảng tin X", "https://x.com/home")]


class RedditScraper(Scraper):
    def __init__(self):
        super().__init__("reddit", REDDIT_JS)

    def urls(self, source_type, sources):
        if source_type == "search" and sources:
            return [(f"Tìm: {s}", f"https://www.reddit.com/search/?q={quote_plus(s)}&sort=new") for s in sources]
        if source_type == "group" and sources:
            return [(s, s if s.startswith("http") else f"https://www.reddit.com/r/{s.removeprefix('r/')}/new/")
                    for s in sources]
        return [("Trang chủ Reddit", "https://www.reddit.com/")]


SCRAPERS: dict[str, type[Scraper]] = {
    "facebook": FacebookScraper,
    "linkedin": LinkedInScraper,
    "x": XScraper,
    "reddit": RedditScraper,
}
