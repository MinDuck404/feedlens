
() => [...document.querySelectorAll('__SELECTOR_1__')].map(n => {
  const t = n.querySelector('__SELECTOR_2__');
  const u = n.querySelector('__SELECTOR_3__');
  const time = n.querySelector('__SELECTOR_4__');
  const link = time && time.closest('__SELECTOR_5__') ? time.closest('__SELECTOR_5__').href : '';
  return { author: u ? u.innerText.split('\n').slice(0, 2).join(' ') : '', text: t ? t.innerText : '',
           url: link, posted_at: time ? time.getAttribute('datetime') : '' };
}).filter(p => p.text.length > 5)
