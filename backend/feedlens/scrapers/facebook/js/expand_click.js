
(indices) => {
  const wanted = new Set(indices || []);
  let clicked = 0;
  document.querySelectorAll('__SELECTOR_17__').forEach(b => {
    const id = Number(b.getAttribute('data-feedlens-expand'));
    b.removeAttribute('data-feedlens-expand');
    if (wanted.has(id)) { try { b.click(); clicked++; } catch (e) {} }
  });
  return clicked;
}
