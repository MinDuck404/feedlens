
(root) => {
  const out = [];
  const cards = window.__feedlensCards ||= { keys: new WeakMap(), next: 0 };
  if (!root) document.querySelectorAll('__SELECTOR_5__').forEach(n => n.removeAttribute('data-feedlens-node'));
  const nodes = root ? [root] : document.querySelectorAll('__NODES__');
  for (const [nodeIndex, n] of [...nodes].entries()) {
    // Feed wrappers and nested shared articles must not produce duplicate posts.
    const article = '__SELECTOR_6__';
    if (!root && !n.matches(article) && n.querySelector(article)) continue;
    if (!root && n.parentElement?.closest(article)) continue;
    if (!root) n.setAttribute('data-feedlens-node', String(nodeIndex));
    const msg = n.querySelector('__SELECTOR_4__');
    let text = msg ? msg.innerText : '';
    if (!text) {
      const blocks = [...n.querySelectorAll('__SELECTOR_7__')].map(d => d.innerText).filter(t => t && t.length > 20);
      text = blocks.sort((a, b) => b.length - a.length)[0] || '';
    }
    if (!text || text.length < 15) continue;
    const authorEl = n.querySelector('__SELECTOR_8__');
    const anchors = [...n.querySelectorAll('__LINKS__')];
    const timestamp = a => {
      if (a.closest('__SELECTOR_9__')) return false;
      if (a.querySelector('__SELECTOR_10__') || a.hasAttribute('data-utime') ||
          /timestamp/i.test(a.getAttribute('data-testid') || '')) return true;
      const referenced = (a.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ').trim();
      const label = (referenced || a.innerText || a.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
      return /^(?:\d+\s*(?:s|m|h|d|w|y|sec|min|hr|hrs|hours?|days?|weeks?|minutes?|秒|分钟|小时|天|周|年|giây|phút|giờ|ngày|tuần|năm)(?:\s*(?:ago|前|trước))?|just now|yesterday|vừa xong|hôm qua|刚刚|昨天)$/i.test(label) ||
        /\b(?:January|February|March|April|May|June|July|August|September|October|November|December|tháng)\b|\d{1,4}[\/-]\d{1,2}[\/-]\d{1,4}|\d+月\d+日/i.test(a.getAttribute('aria-label') || '');
    };
    const authorUrl = authorEl?.closest('__SELECTOR_11__')?.getAttribute('href') || authorEl?.querySelector('__SELECTOR_11__')?.getAttribute('href') || '';
    const links = anchors.flatMap(a => [...new Set(['href', 'data-href', 'data-url', 'ajaxify']
      .map(key => a.getAttribute(key)).filter(Boolean))].map(href => [href, timestamp(a)]));
    // Obfuscated timestamps fail the text test; their href is "#" or missing until hover.
    // Real feed (2026-11): the timestamp is <a aria-labelledby=… href="?__cft__…"> until hovered.
    const placeholder = h => !h || h === '#' || h.startsWith('?');
    const lazy = a => !a.closest('__SELECTOR_9__') && placeholder(a.getAttribute('href'))
      && !a.querySelector('img, svg image') && (a.hasAttribute('aria-labelledby') || (a.innerText || '').trim().length <= 40);
    const hover = [...new Set([
      ...anchors.flatMap((a, i) => a.hasAttribute('aria-labelledby') && lazy(a) ? [i] : []),
      ...anchors.flatMap((a, i) => timestamp(a) ? [i] : []),
      ...anchors.flatMap((a, i) => lazy(a) ? [i] : [])])].slice(0, 3);
    const adWords = /^(?:sponsored|được tài trợ|赞助内容|广告)$/i;
    const sponsored = [...n.querySelectorAll('__SELECTOR_12__')].some(el =>
      adWords.test((el.getAttribute('aria-label') || el.innerText || '').trim()))
      || anchors.some(a => /\/ads\/about|[?&]ad_id=/.test(a.getAttribute('href') || ''))
      // Real feed samples (runs 6–10): the obfuscated "Sponsored" label is a header link whose
      // only text is U+2060; organic posts put an aria-labelledby timestamp there instead.
      || anchors.some(a => !a.closest('__SELECTOR_13__') && (a.textContent || '').includes('⁠')
        && /^[⁠​\s]*$/.test(a.textContent || ''));
    if (!cards.keys.has(n)) cards.keys.set(n, ++cards.next);
    out.push({ author: authorEl ? authorEl.innerText.split('\n')[0] : '', text, url: '', links,
      _card_key: performance.timeOrigin + ':' + cards.keys.get(n),
      _node_index: nodeIndex, _node_marker: n.getAttribute('data-feedlens-node'), _hover: hover, _author_url: authorUrl, posted_at: '', sponsored });
  }
  return out;
}
