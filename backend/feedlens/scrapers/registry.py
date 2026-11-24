"""Platform scraper selection used by run collection."""
from .base import Scraper
from .facebook.scraper import FacebookScraper
from .linkedin.scraper import LinkedInScraper
from .x.scraper import XScraper
from .reddit.scraper import RedditScraper

SCRAPERS: dict[str, type[Scraper]] = {
    "facebook": FacebookScraper,
    "linkedin": LinkedInScraper,
    "x": XScraper,
    "reddit": RedditScraper,
}
