"""Bộ lướt cho từng nền tảng.

Mỗi nền tảng khai báo: URL cần mở theo loại nguồn (feed/group/search) và một đoạn JS
trích xuất bài viết đang hiển thị. Vòng lặp cuộn chung xử lý nhịp độ giống người,
khử trùng lặp và dừng khi đủ số bài hoặc hết nội dung mới.

Selector của mạng xã hội thay đổi thường xuyên — khi một nền tảng ngừng trả bài,
hãy sửa đoạn JS tương ứng trong file này.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote_plus

from playwright.sync_api import Page

from .models import RawPost

ProgressFn = Callable[[int, str], None]

# --- JS extractors: trả về [{author, text, url, posted_at}] ---------------------------

FB_JS = r"""
() => {
  const out = [];
  const nodes = document.querySelectorAll('div[role="feed"] > div, div[role="article"][aria-posinset], div[aria-posinset]');
  for (const n of nodes) {
    const msg = n.querySelector('[data-ad-preview="message"], [data-ad-comet-preview="message"]');
    let text = msg ? msg.innerText : '';
    if (!text) {
      const blocks = [...n.querySelectorAll('div[dir="auto"]')].map(d => d.innerText).filter(t => t && t.length > 20);
      text = blocks.sort((a, b) => b.length - a.length)[0] || '';
    }
    if (!text || text.length < 15) continue;
    const authorEl = n.querySelector('h2 a, h3 a, h4 a, strong a, h2, h3, h4');
    const link = [...n.querySelectorAll('a[href]')].map(a => a.href)
      .find(h => /\/(posts|permalink|videos|photo)\/|story_fbid=|\/groups\/[^/]+\/posts\//.test(h)) || '';
    out.push({ author: authorEl ? authorEl.innerText.split('\n')[0] : '', text, url: link.split('?__cft__')[0], posted_at: '' });
  }
  return out;
}
"""

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
        stale_rounds = 0
        while len(posts) < target and stale_rounds < pace["stale"]:
            if self.ensure_access(page, url, progress, interactive):
                stale_rounds = 0  # vừa xác minh xong và đã mở lại trang
            if self.expand_js:
                page.evaluate(self.expand_js)
                _human_pause(*pace["expand"])
            before = len(posts)
            for item in page.evaluate(self.extract_js):
                p = RawPost(platform=self.platform, source=label, **item)
                fp = p.fingerprint
                if fp in seen:
                    continue
                seen.add(fp)
                posts.append(p)
                if len(posts) >= target:
                    break
            stale_rounds = stale_rounds + 1 if len(posts) == before else 0
            progress(len(posts), f"{label}: {len(posts)}/{target}")
            page.mouse.wheel(0, random.randint(*pace["scroll"]))
            _human_pause(*pace["pause"])
            if random.random() < pace["long_chance"]:  # thỉnh thoảng dừng lâu như đang đọc
                _human_pause(*pace["long"])
        return posts

    def blocked(self, url: str) -> bool:
        return is_blocked_url(self.platform, url)

    def ensure_access(self, page: Page, url: str, progress: ProgressFn, interactive: bool) -> bool:
        """Nếu nền tảng chuyển sang trang đăng nhập / xác minh 2 bước / checkpoint:
        - có cửa sổ: chờ người dùng tự xác minh (không tự giải CAPTCHA), rồi mở lại trang cần lướt;
        - chạy ẩn: báo lỗi rõ ràng thay vì lướt ra 0 bài.
        Trả về True nếu đã phải chờ và mở lại trang."""
        if not self.blocked(page.url):
            return False
        if not interactive:
            raise NeedsVerification(
                f"{self.platform} đang yêu cầu đăng nhập hoặc xác minh. Tắt chế độ chạy ẩn để xác minh "
                f"trong cửa sổ Chrome, hoặc chạy `feedlens login {self.platform}`.")
        deadline = time.time() + VERIFY_TIMEOUT
        while self.blocked(page.url):
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
