
() => {
  const labels = ['See more', 'Xem thêm'];
  const out = [];
  document.querySelectorAll('__SELECTOR_17__').forEach(b => b.removeAttribute('data-feedlens-expand'));
  document.querySelectorAll('__SELECTOR_16__').forEach((b, idx) => {
    if (!labels.includes((b.innerText || '').trim())) return;
    const n = b.closest('__SELECTOR_18__');
    if (!n) return;
    const msg = n.querySelector('__SELECTOR_4__');
    let text = msg ? msg.innerText : '';
    if (!text) {
      const blocks = [...n.querySelectorAll('__SELECTOR_7__')].map(d => d.innerText).filter(t => t && t.length > 20);
      text = blocks.sort((a, b) => b.length - a.length)[0] || '';
    }
    const authorEl = n.querySelector('__SELECTOR_8__');
    b.setAttribute('data-feedlens-expand', String(idx));
    const links = [...n.querySelectorAll('__SELECTOR_19__')]
      .filter(a => a.closest('__SELECTOR_18__') === n)
      .map(a => a.getAttribute('href'));
    out.push({ idx, author: authorEl ? authorEl.innerText.split('\n')[0] : '', text, links });
  });
  return out;
}
