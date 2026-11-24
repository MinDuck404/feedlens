"""Read LinkedIn job result cards; URL parameters/selectors need live UI verification."""
from __future__ import annotations

from feedlens.scrapers.scripts import load_script
from feedlens.scrapers.linkedin.selectors import SELECTORS


from collections.abc import Sequence
from urllib.parse import parse_qsl
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

from playwright.sync_api import Page


WORK_MODES = {"remote": "2", "hybrid": "3", "onsite": "1"}
POSTED_WITHIN = {"day": "r86400", "week": "r604800", "month": "r2592000"}


def jobs_search_url(keywords: str, location: str = "", work_modes: Sequence[str] = (),
                    posted_within: str = "week") -> str:
    """Build one Jobs search without navigating or using session credentials."""
    if posted_within not in POSTED_WITHIN:
        raise ValueError(f"Unknown posted_within: {posted_within}")
    if any(mode not in WORK_MODES for mode in work_modes):
        raise ValueError("Unknown LinkedIn work mode")
    params = {"keywords": keywords.strip()}
    if location.strip():
        params["location"] = location.strip()
    if work_modes:
        params["f_WT"] = ",".join(dict.fromkeys(WORK_MODES[mode] for mode in work_modes))
    params.update(f_TPR=POSTED_WITHIN[posted_within], sortBy="DD")
    return "https://www.linkedin.com/jobs/search/?" + urlencode(params)


def next_jobs_page_url(url: str) -> str:
    """Advance a Jobs search offset by 25, retaining its search filters."""
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname not in {"linkedin.com", "www.linkedin.com"}
            or parts.username or parts.password or parts.port not in {None, 443}
            or parts.path.rstrip("/") != "/jobs/search"):
        raise ValueError("Expected a LinkedIn Jobs search URL")
    params = parse_qsl(parts.query, keep_blank_values=True)
    offsets = [value for key, value in params if key == "start"]
    if len(offsets) > 1 or (offsets and not offsets[0].isascii()) or (offsets and not offsets[0].isdigit()):
        raise ValueError("Expected one nonnegative start offset")
    start = int(offsets[0]) if offsets else 0
    params = [(key, value) for key, value in params if key != "start"]
    params.append(("start", str(start + 25)))
    return urlunsplit(("https", "www.linkedin.com", "/jobs/search/", urlencode(params), ""))


JOB_CARDS_JS = load_script("feedlens.scrapers.linkedin", 'job_cards.js', SELECTORS)


def extract_job_cards(page: Page) -> list[dict]:
    """Return rendered result-card facts without clicking, scrolling or navigating."""
    return page.evaluate(JOB_CARDS_JS)
