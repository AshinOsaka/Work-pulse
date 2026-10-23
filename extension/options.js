const DEFAULTS = { enabled: true, port: 47113, token: '' };

async function init() {
  const cfg = { ...DEFAULTS, ...(await chrome.storage.local.get(DEFAULTS)) };
  document.getElementById('port').value = cfg.port;
  document.getElementById('token').value = cfg.token;
  document.getElementById('save').addEventListener('click', save);
}

async function save() {
  const port = Number.parseInt(document.getElementById('port').value, 10);
  const token = document.getElementById('token').value.trim();
  if (!Number.isInteger(port) || port < 1 || port > 65535) return;
  await chrome.storage.local.set({ port, token });
  const saved = document.getElementById('saved');
  saved.hidden = false;
  setTimeout(() => (saved.hidden = true), 1500);
}

void init();
