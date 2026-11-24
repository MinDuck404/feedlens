
() => [...document.querySelectorAll('__SELECTOR_4__')]
  .slice(-30).map(n => (n.textContent || '').trim().slice(0, 240)).filter(Boolean)
