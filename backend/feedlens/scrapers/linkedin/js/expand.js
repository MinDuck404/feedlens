
() => {
  let clicked = 0;
  document.querySelectorAll('__SELECTOR_36__').forEach(b => {
    try { b.click(); clicked++; } catch (e) {}
  });
  return clicked;
}
