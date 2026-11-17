"""Read LinkedIn job result cards; URL parameters/selectors need live UI verification."""
from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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


JOB_CARDS_JS = r"""
() => {
  const clean = value => (value || '').replace(/\s+/g, ' ').trim();
  const text = (node, selectors) => {
    for (const selector of selectors) {
      const element = node.matches(selector) ? node : node.querySelector(selector);
      const value = element && clean(element.innerText);
      if (value) return value;
    }
    return '';
  };
  const linkId = anchor => {
    try {
      const url = new URL(anchor.getAttribute('href'), 'https://www.linkedin.com');
      if (url.protocol !== 'https:' || !['linkedin.com', 'www.linkedin.com'].includes(url.hostname)
          || url.username || url.password || (url.port && url.port !== '443')) return '';
      return url.pathname.match(/^\/jobs\/view\/(?:[^/]+-)?(\d+)\/?$/)?.[1] || '';
    } catch { return ''; }
  };
  const cardSelector = '[data-job-id], [data-occludable-job-id], .job-card-container, .job-card-list, .base-search-card';
  const roots = [...document.querySelectorAll('.jobs-search-results-list, .jobs-search__results-list, .scaffold-layout__list, .jobs-search-results__list')];
  const candidates = new Set();
  for (const root of roots.length ? roots : [document]) {
    root.querySelectorAll(cardSelector).forEach(node => candidates.add(node));
    root.querySelectorAll('a[href*="/jobs/view/"]').forEach(anchor => {
      candidates.add(anchor.closest(cardSelector) || anchor.closest('li') || anchor.parentElement);
    });
  }
  const jobs = new Map();
  for (const node of candidates) {
    if (!node || !node.getClientRects().length || node.closest('[hidden], [aria-hidden="true"], .scaffold-layout__detail, .jobs-details, .jobs-search__job-details--container')) continue;
    const ids = ['data-job-id', 'data-occludable-job-id'].map(key => node.getAttribute(key)).filter(value => /^\d+$/.test(value || ''));
    const links = [...node.querySelectorAll('a[href*="/jobs/view/"]')];
    const linkIds = [...new Set(links.map(linkId).filter(Boolean))];
    const allIds = [...new Set([...ids, ...linkIds])];
    // A recycled/mixed card must not attach another job's title to this identity.
    if (allIds.length !== 1) continue;
    const jobId = allIds[0];
    const titleLink = links.find(anchor => linkId(anchor) === jobId);
    const title = clean(node.getAttribute('data-job-title')) || text(node, [
      '.job-card-list__title--link [aria-hidden="true"]', '.job-card-list__title [aria-hidden="true"]',
      '.job-card-list__title--link', '.job-card-list__title', '.job-card-container__link',
      '.base-search-card__title', 'h3'
    ]) || clean(titleLink?.getAttribute('aria-label') || titleLink?.innerText);
    if (!title) continue;
    const company = clean(node.getAttribute('data-company-name')) || text(node, [
      '.job-card-container__primary-description', '.artdeco-entity-lockup__subtitle',
      '.base-search-card__subtitle', '[data-company-name]', 'a[href*="/company/"]'
    ]);
    const location = clean(node.getAttribute('data-job-location')) || text(node, [
      '.job-card-container__metadata-item', '.artdeco-entity-lockup__caption',
      '.job-search-card__location', '[data-job-location]'
    ]);
    const time = node.querySelector('time');
    const postedAt = clean(time?.getAttribute('datetime')) || text(node, [
      'time', '.job-card-container__listed-time', '.job-search-card__listdate', '.job-search-card__listdate--new'
    ]);
    const salaryText = text(node, ['.job-card-container__salary-info', '.job-search-card__salary-info', '[data-salary]']);
    const modeText = clean(node.getAttribute('data-work-mode') || text(node, ['[data-work-mode]']) || location);
    const modes = [
      ['remote', /\bremote\b|từ xa|远程/i],
      ['hybrid', /\bhybrid\b|kết hợp|混合/i],
      ['onsite', /\bon[ -]?site\b|tại văn phòng|现场/i]
    ].filter(([, pattern]) => pattern.test(modeText)).map(([mode]) => mode);
    const workMode = modes.length === 1 ? modes[0] : '';
    const snippet = text(node, ['.job-card-container__description', '.job-search-card__snippet', '[data-job-description]']);
    const url = `https://www.linkedin.com/jobs/view/${jobId}/`;
    const seed = {title, company, location, url, job_id: jobId, posted_at: postedAt, work_mode: workMode, salary_text: salaryText};
    const item = {text: [...new Set([title, company, location, snippet, salaryText].filter(Boolean))].join('\n'), author: company, url, posted_at: postedAt, job_seed: seed};
    const previous = jobs.get(jobId);
    if (!previous) jobs.set(jobId, item);
    else {
      // Duplicate wrappers often reveal different amounts of the same card.
      for (const key of ['company', 'location', 'posted_at', 'work_mode', 'salary_text']) {
        if (!previous.job_seed[key] && seed[key]) previous.job_seed[key] = seed[key];
      }
      previous.author = previous.job_seed.company;
      previous.posted_at = previous.job_seed.posted_at;
      if (item.text.length > previous.text.length) previous.text = item.text;
    }
  }
  return [...jobs.values()];
}
"""


def extract_job_cards(page: Page) -> list[dict]:
    """Return rendered result-card facts without clicking, scrolling or navigating."""
    return page.evaluate(JOB_CARDS_JS)
