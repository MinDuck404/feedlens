
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
  const cardSelector = '__SELECTOR_1__';
  const roots = [...document.querySelectorAll('__SELECTOR_2__')];
  const candidates = new Set();
  for (const root of roots.length ? roots : [document]) {
    root.querySelectorAll(cardSelector).forEach(node => candidates.add(node));
    root.querySelectorAll('__SELECTOR_3__').forEach(anchor => {
      candidates.add(anchor.closest(cardSelector) || anchor.closest('li') || anchor.parentElement);
    });
  }
  const jobs = new Map();
  for (const node of candidates) {
    if (!node || !node.getClientRects().length || node.closest('__SELECTOR_4__')) continue;
    const ids = ['data-job-id', 'data-occludable-job-id'].map(key => node.getAttribute(key)).filter(value => /^\d+$/.test(value || ''));
    const links = [...node.querySelectorAll('__SELECTOR_3__')];
    const linkIds = [...new Set(links.map(linkId).filter(Boolean))];
    const allIds = [...new Set([...ids, ...linkIds])];
    // A recycled/mixed card must not attach another job's title to this identity.
    if (allIds.length !== 1) continue;
    const jobId = allIds[0];
    const titleLink = links.find(anchor => linkId(anchor) === jobId);
    const title = clean(node.getAttribute('data-job-title')) || text(node, [
      '__SELECTOR_5__', '__SELECTOR_6__',
      '__SELECTOR_7__', '__SELECTOR_8__', '__SELECTOR_9__',
      '__SELECTOR_10__', '__SELECTOR_11__'
    ]) || clean(titleLink?.getAttribute('aria-label') || titleLink?.innerText);
    if (!title) continue;
    const company = clean(node.getAttribute('data-company-name')) || text(node, [
      '__SELECTOR_12__', '__SELECTOR_13__',
      '__SELECTOR_14__', '__SELECTOR_15__', '__SELECTOR_16__'
    ]);
    const location = clean(node.getAttribute('data-job-location')) || text(node, [
      '__SELECTOR_17__', '__SELECTOR_18__',
      '__SELECTOR_19__', '__SELECTOR_20__'
    ]);
    const time = node.querySelector('__SELECTOR_21__');
    const postedAt = clean(time?.getAttribute('datetime')) || text(node, [
      '__SELECTOR_21__', '__SELECTOR_22__', '__SELECTOR_23__', '__SELECTOR_24__'
    ]);
    const salaryText = text(node, ['__SELECTOR_25__', '__SELECTOR_26__', '__SELECTOR_27__']);
    const modeText = clean(node.getAttribute('data-work-mode') || text(node, ['__SELECTOR_28__']) || location);
    const modes = [
      ['remote', /\bremote\b|từ xa|远程/i],
      ['hybrid', /\bhybrid\b|kết hợp|混合/i],
      ['onsite', /\bon[ -]?site\b|tại văn phòng|现场/i]
    ].filter(([, pattern]) => pattern.test(modeText)).map(([mode]) => mode);
    const workMode = modes.length === 1 ? modes[0] : '';
    const snippet = text(node, ['__SELECTOR_29__', '__SELECTOR_30__', '__SELECTOR_31__']);
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
