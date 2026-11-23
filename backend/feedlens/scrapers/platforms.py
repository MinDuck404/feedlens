"""Platform URLs and extraction scripts."""
from __future__ import annotations

from urllib.parse import quote_plus
from playwright.sync_api import Page
from .base import Scraper
from .facebook_dom import FB_EXPAND_JS, FB_JS


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
() => {
  let clicked = 0;
  document.querySelectorAll('button.feed-shared-inline-show-more-text__see-more-less-toggle, .see-more').forEach(b => {
    try { b.click(); clicked++; } catch (e) {}
  });
  return clicked;
}
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


class LinkedInJobsScraper(Scraper):
    """Read result cards only; use the common budget, deduplication and reporting loop."""
    def __init__(self):
        super().__init__("linkedin", "")

    def extract_items(self, page: Page, stories: dict) -> list[dict]:
        from ..scrapers_linkedin_jobs import extract_job_cards
        return extract_job_cards(page)

    def next_page(self, url: str) -> str:
        from ..scrapers_linkedin_jobs import next_jobs_page_url
        return next_jobs_page_url(url)

    def scroll(self, page: Page, distance: int) -> None:
        scrolled = page.evaluate("""distance => {
          const list = document.querySelector('.jobs-search-results-list, .scaffold-layout__list, .jobs-search-results');
          if (!list) return false;
          list.scrollBy(0, distance); return true;
        }""", distance)
        if not scrolled:
            super().scroll(page, distance)


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
