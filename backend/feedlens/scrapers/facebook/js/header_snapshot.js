
(n) => {
  const keep = new Set(['href', 'data-href', 'data-url', 'ajaxify', 'role', 'aria-label', 'aria-labelledby',
    'aria-hidden', 'data-ad-preview', 'data-ad-comet-preview', 'data-testid', 'data-utime', 'dir', 'id',
    'data-post-id', 'data-story-id', 'data-video-id']);
  const clean = root => {
    root.querySelectorAll('img, svg, video, picture, style, script, input').forEach(e => e.remove());
    for (const el of [root, ...root.querySelectorAll('__SELECTOR_14__')]) {
      for (const at of [...el.attributes]) {
        if (!keep.has(at.name)) { el.removeAttribute(at.name); continue; }
        if (['href','data-href','data-url','ajaxify'].includes(at.name)) {
          try {
            const u = new URL(at.value, 'https://www.facebook.com/');
            if (!['https:', 'http:'].includes(u.protocol)) { el.removeAttribute(at.name); continue; }
            for (const k of [...u.searchParams.keys()]) if (/token|cookie|auth|session|secret|credential|dtsg|^__|^(?:fbclid|eav|paipv|_rdr|lsd|jazoest|h|u)$/i.test(k)) u.searchParams.delete(k);
            u.hash = ''; el.setAttribute(at.name, u.href);
          } catch { el.removeAttribute(at.name); }
        } else if (at.value.length > 200) el.setAttribute(at.name, at.value.slice(0, 200));
      }
    }
    const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let t = walk.nextNode(); t; t = walk.nextNode()) if (t.nodeValue.length > 30) t.nodeValue = t.nodeValue.slice(0, 30) + '…';
    return root;
  };
  const result = document.createElement('section');
  result.setAttribute('data-feedlens-snapshot', '2');
  const links = document.createElement('nav'); links.setAttribute('data-feedlens-links', '');
  // Preserve late permalinks before pruning noisy/obfuscated context; never slice raw HTML.
  const anchors = [...n.querySelectorAll('__LINKS__')];
  anchors.sort((a,b) => Number(/pfbid|story_fbid|fbid|\/posts\/|\/permalink\//i.test(b.getAttribute('href') || '')) - Number(/pfbid|story_fbid|fbid|\/posts\/|\/permalink\//i.test(a.getAttribute('href') || '')));
  for (const a of anchors.slice(0, 100)) {
    const c = a.cloneNode(false); c.textContent = (a.innerText || a.textContent || '').slice(0, 30);
    clean(c);
    if (links.outerHTML.length + c.outerHTML.length > 24000) continue;
    links.append(c);
    for (const id of (a.getAttribute('aria-labelledby') || '').split(/\s+/)) {
      const ref = document.getElementById(id);
      if (ref && links.outerHTML.length < 23000) {
        const label = document.createElement('span'); label.id = id; label.textContent = ref.textContent.slice(0, 30); links.append(clean(label));
      }
    }
  }
  result.append(links);
  const context = clean(n.cloneNode(true));
  context.querySelectorAll('__SELECTOR_15__').forEach(e => { if (e.textContent.trim() === 'Facebook') e.remove(); });
  [...context.querySelectorAll('__SELECTOR_14__')].slice(300).forEach(e => e.remove());
  while (context.outerHTML.length > 12000 && context.lastElementChild) context.lastElementChild.remove();
  result.append(context);
  return result.outerHTML;
}
