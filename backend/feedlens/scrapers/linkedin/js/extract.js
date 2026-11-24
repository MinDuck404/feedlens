
() => [...document.querySelectorAll('__SELECTOR_32__')].map(n => {
  const t = n.querySelector('__SELECTOR_33__');
  const a = n.querySelector('__SELECTOR_34__');
  const urn = n.getAttribute('data-urn') || (n.closest('__SELECTOR_35__') || {getAttribute: () => ''}).getAttribute('data-urn');
  return { author: a ? a.innerText.trim() : '', text: t ? t.innerText.trim() : '',
           url: urn ? 'https://www.linkedin.com/feed/update/' + urn + '/' : '', posted_at: '' };
}).filter(p => p.text.length > 15)
