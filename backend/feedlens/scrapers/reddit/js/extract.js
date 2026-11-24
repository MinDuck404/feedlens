
() => [...document.querySelectorAll('__SELECTOR_1__')].map(n => {
  const body = n.querySelector('__SELECTOR_2__');
  const title = n.getAttribute('post-title') || '';
  return { author: n.getAttribute('author') || '', text: (title + '\n' + (body ? body.innerText : '')).trim(),
           url: 'https://www.reddit.com' + (n.getAttribute('permalink') || ''),
           posted_at: n.getAttribute('created-timestamp') || '' };
}).filter(p => p.text.length > 5)
