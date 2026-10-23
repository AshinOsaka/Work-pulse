const DEFAULTS = { enabled: true, port: 47113, token: '' };

async function settings() {
  const stored = await chrome.storage.local.get(DEFAULTS);
  return { ...DEFAULTS, ...stored };
}

async function refreshStatus() {
  const el = document.getElementById('status');
  const cfg = await settings();
  try {
    const res = await fetch(`http://127.0.0.1:${cfg.port}/health`, { method: 'GET' });
    const body = await res.json();
    if (res.ok && body.app === 'workpulse-agent') {
      el.textContent = 'Connected';
      el.className = 'status ok';
      return;
    }
    throw new Error('unexpected');
  } catch {
    el.textContent = 'Not running';
    el.className = 'status off';
  }
}

async function init() {
  const cfg = await settings();
  const toggle = document.getElementById('enabled');
  toggle.checked = cfg.enabled;
  toggle.addEventListener('change', () => chrome.storage.local.set({ enabled: toggle.checked }));
  document.getElementById('options').addEventListener('click', (e) => {
    e.preventDefault();
    chrome.runtime.openOptionsPage();
  });
  await refreshStatus();
}

void init();
