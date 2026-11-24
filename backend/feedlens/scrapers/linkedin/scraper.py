"""Linkedin navigation and extraction."""
from __future__ import annotations

from feedlens.scrapers.scripts import load_script
from feedlens.scrapers.linkedin.selectors import SELECTORS

LINKEDIN_SCROLL_JOBS_JS = load_script("feedlens.scrapers.linkedin", 'scroll_jobs.js', SELECTORS)

from urllib.parse import quote_plus
from playwright.sync_api import Page
from feedlens.scrapers.base import Scraper


LINKEDIN_JS = load_script("feedlens.scrapers.linkedin", 'extract.js', SELECTORS)


LINKEDIN_EXPAND_JS = load_script("feedlens.scrapers.linkedin", 'expand.js', SELECTORS)


class LinkedInJobsScraper(Scraper):
    """Read result cards only; use the common budget, deduplication and reporting loop."""
    def __init__(self):
        super().__init__("linkedin", "")

    def extract_items(self, page: Page, stories: dict) -> list[dict]:
        from feedlens.scrapers.linkedin.jobs import extract_job_cards
        return extract_job_cards(page)

    def next_page(self, url: str) -> str:
        from feedlens.scrapers.linkedin.jobs import next_jobs_page_url
        return next_jobs_page_url(url)

    def scroll(self, page: Page, distance: int) -> None:
        scrolled = page.evaluate(LINKEDIN_SCROLL_JOBS_JS, distance)
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
