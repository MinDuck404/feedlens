from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from feedlens.scrapers_linkedin_jobs import extract_job_cards, jobs_search_url, next_jobs_page_url


FIXTURES = Path(__file__).parent / "fixtures" / "linkedin_jobs"


def test_search_url_encodes_keywords_location_and_filters():
    url = jobs_search_url("Python & C++", "Hồ Chí Minh / Việt Nam", ["remote", "hybrid", "remote"], "day")
    assert url.startswith("https://www.linkedin.com/jobs/search/?")
    assert parse_qs(urlsplit(url).query) == {
        "keywords": ["Python & C++"], "location": ["Hồ Chí Minh / Việt Nam"],
        "f_WT": ["2,3"], "f_TPR": ["r86400"], "sortBy": ["DD"],
    }


@pytest.mark.parametrize("period,expected", [("day", "r86400"), ("week", "r604800"), ("month", "r2592000")])
def test_search_periods_and_no_workplace_filter(period, expected):
    params = parse_qs(urlsplit(jobs_search_url("  developer  ", posted_within=period)).query)
    assert params == {"keywords": ["developer"], "f_TPR": [expected], "sortBy": ["DD"]}


def test_search_defaults_and_onsite():
    assert parse_qs(urlsplit(jobs_search_url("Python", work_modes=["onsite"])).query)["f_WT"] == ["1"]
    assert parse_qs(urlsplit(jobs_search_url("Python")).query)["f_TPR"] == ["r604800"]


@pytest.mark.parametrize("kwargs", [{"work_modes": ["anywhere"]}, {"posted_within": "today"}])
def test_search_rejects_unknown_filters(kwargs):
    with pytest.raises(ValueError):
        jobs_search_url("Python", **kwargs)


def test_pagination_advances_offset_and_preserves_filters():
    original = jobs_search_url("C++ & Python", "Việt Nam", ["remote", "onsite"], "month")
    second = next_jobs_page_url(original)
    third = next_jobs_page_url(second)
    assert parse_qs(urlsplit(second).query) == {**parse_qs(urlsplit(original).query), "start": ["25"]}
    assert parse_qs(urlsplit(third).query)["start"] == ["50"]


@pytest.mark.parametrize("url", [
    "https://evil.test/jobs/search/", "https://linkedin.com.evil.test/jobs/search/",
    "http://www.linkedin.com/jobs/search/", "https://www.linkedin.com/jobs/view/123/",
    "https://user:password@www.linkedin.com/jobs/search/", "https://www.linkedin.com/jobs/search/?start=-1",
    "https://www.linkedin.com/jobs/search/?start=x", "https://www.linkedin.com/jobs/search/?start=0&start=25",
])
def test_pagination_rejects_wrong_urls_and_invalid_offsets(url):
    with pytest.raises(ValueError):
        next_jobs_page_url(url)


@pytest.fixture(scope="module")
def jobs_page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(service_workers="block")
        page.route("**/*", lambda route: route.abort())
        yield page
        browser.close()


def test_result_cards_are_deduplicated_and_keep_observed_job_facts(jobs_page):
    jobs_page.set_content((FIXTURES / "results.html").read_text(encoding="utf-8"))
    cards = extract_job_cards(jobs_page)
    assert len(cards) == 2
    assert cards[0] == {
        "text": "Python Engineer\nExample Labs\nHồ Chí Minh, Vietnam (Remote)\nBuild FastAPI services.\n$80,000–$100,000/year",
        "author": "Example Labs", "url": "https://www.linkedin.com/jobs/view/4100000001/",
        "posted_at": "2026-11-17T08:30:00Z",
        "job_seed": {"title": "Python Engineer", "company": "Example Labs",
                     "location": "Hồ Chí Minh, Vietnam (Remote)", "url": "https://www.linkedin.com/jobs/view/4100000001/",
                     "job_id": "4100000001", "posted_at": "2026-11-17T08:30:00Z",
                     "work_mode": "remote", "salary_text": "$80,000–$100,000/year"},
    }
    assert cards[1]["job_seed"]["work_mode"] == "hybrid"
    assert cards[1]["posted_at"] == "1 day ago"  # Do not invent an exact timestamp.
    assert cards[1]["job_seed"]["salary_text"] == ""
    assert jobs_page.url == "about:blank"
    assert jobs_page.evaluate("window.applied === true") is False


def test_public_markup_and_anchor_fallback_do_not_borrow_company_mode(jobs_page):
    jobs_page.set_content((FIXTURES / "fallbacks.html").read_text(encoding="utf-8"))
    cards = extract_job_cards(jobs_page)
    assert [card["job_seed"]["job_id"] for card in cards] == ["4100000010", "4100000011"]
    assert cards[0]["job_seed"]["title"] == "UX Designer"
    assert cards[0]["job_seed"]["work_mode"] == "onsite"
    assert cards[1]["job_seed"]["title"] == "Research Engineer"
    assert cards[1]["job_seed"]["company"] == "Remote Example Ltd"
    assert cards[1]["job_seed"]["work_mode"] == ""
    assert "Research search relevance." in cards[1]["text"]


def test_id_only_card_and_ambiguous_workplace_preserve_unknowns(jobs_page):
    jobs_page.set_content('<div data-occludable-job-id="123" data-job-title="Engineer" '
                          'data-job-location="Vietnam (Remote / Hybrid)"></div>')
    card = extract_job_cards(jobs_page)[0]
    assert card["url"] == "https://www.linkedin.com/jobs/view/123/"
    assert card["job_seed"]["work_mode"] == ""
    assert card["author"] == card["posted_at"] == ""


def test_unknown_layout_returns_no_jobs_and_does_not_click(jobs_page):
    jobs_page.set_content('<h1>Login required or an unknown layout</h1><button onclick="window.clicked=true">Apply</button>')
    assert extract_job_cards(jobs_page) == []
    assert jobs_page.evaluate("window.clicked === true") is False
