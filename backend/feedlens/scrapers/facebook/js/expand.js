
() => {
  const labels = ['See more', 'Xem thêm'];
  let clicked = 0;
  document.querySelectorAll('__SELECTOR_16__').forEach(b => {
    if (labels.includes((b.innerText || '').trim())) { try { b.click(); clicked++; } catch (e) {} }
  });
  return clicked;
}
