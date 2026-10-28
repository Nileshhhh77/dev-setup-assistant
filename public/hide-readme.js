(() => {
  const hideReadme = () => {
    document.querySelectorAll('header button, header a').forEach((element) => {
      if ((element.textContent || '').trim().toLowerCase() === 'readme') {
        element.hidden = true;
        element.style.display = 'none';
      }
    });
  };
  hideReadme();
  new MutationObserver(hideReadme).observe(document.documentElement, { childList: true, subtree: true });
})();
