(() => {
  const key = 'dev-assistant-theme';
  const root = document.documentElement;
  const stored = localStorage.getItem(key);
  const initial = stored || 'light';
  root.dataset.theme = initial;

  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'theme-toggle';
  button.setAttribute('aria-label', 'Toggle light and dark mode');
  const render = () => {
    const dark = root.dataset.theme === 'dark';
    button.textContent = dark ? '☀' : '☾';
    button.title = dark ? 'Switch to light mode' : 'Switch to dark mode';
  };
  button.addEventListener('click', () => {
    root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem(key, root.dataset.theme);
    render();
  });
  document.body.appendChild(button);
  render();

  const observer = new MutationObserver(() => {
    const dark = document.body.classList.contains('dark') || document.body.classList.contains('dark-mode') || document.documentElement.classList.contains('dark') || document.documentElement.getAttribute('data-mui-color-scheme') === 'dark';
    if (dark && root.dataset.theme !== 'dark') {
      root.dataset.theme = 'dark';
      render();
    } else if (!dark && root.dataset.theme !== 'light' && document.documentElement.getAttribute('data-mui-color-scheme') === 'light') {
      root.dataset.theme = 'light';
      render();
    }
  });
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-mui-color-scheme', 'data-theme'] });
  observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
})();
