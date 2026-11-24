"""Reddit navigation and extraction."""
from __future__ import annotations

from feedlens.scrapers.scripts import load_script
from feedlens.scrapers.reddit.selectors import SELECTORS


from urllib.parse import quote_plus
from playwright.sync_api import Page
from feedlens.scrapers.base import Scraper


REDDIT_JS = load_script("feedlens.scrapers.reddit", 'extract.js', SELECTORS)


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
