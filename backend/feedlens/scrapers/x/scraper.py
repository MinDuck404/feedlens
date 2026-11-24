"""X navigation and extraction."""
from __future__ import annotations

from feedlens.scrapers.scripts import load_script
from feedlens.scrapers.x.selectors import SELECTORS


from urllib.parse import quote_plus
from playwright.sync_api import Page
from feedlens.scrapers.base import Scraper


X_JS = load_script("feedlens.scrapers.x", 'extract.js', SELECTORS)


class XScraper(Scraper):
    def __init__(self):
        super().__init__("x", X_JS)

    def urls(self, source_type, sources):
        if source_type == "search" and sources:
            return [(f"Tìm: {s}", f"https://x.com/search?q={quote_plus(s)}&f=live") for s in sources]
        if source_type == "group" and sources:  # list hoặc community URL / @user
            return [(s, s if s.startswith("http") else f"https://x.com/{s.lstrip('@')}") for s in sources]
        return [("Bảng tin X", "https://x.com/home")]
