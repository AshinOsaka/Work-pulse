// Applies the persisted theme before first paint (loaded synchronously from <head>, so there is no flash).
// Kept as a same-origin file so the Content-Security-Policy can forbid inline scripts.
;(function () {
  try {
    var stored = JSON.parse(localStorage.getItem('wp.ui') || '{}')
    var theme = (stored.state && stored.state.theme) || 'system'
    var dark = theme === 'dark' || (theme === 'system' && matchMedia('(prefers-color-scheme: dark)').matches)
    if (dark) document.documentElement.classList.add('dark')
  } catch (e) {}
})()
