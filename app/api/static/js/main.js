document.addEventListener('DOMContentLoaded', () => {
  const saved = localStorage.getItem('banter-theme');
  if (saved) document.documentElement.setAttribute('data-theme', saved);
});
