// WorkPulse Website Reporter — background service worker.
//
// Privacy: this extension reads ONLY the host name of your active tab (e.g. "github.com"), never the
// full URL, path, query, page title or content, and never for incognito/private windows. It sends that
// host over the loopback interface (127.0.0.1) to the WorkPulse agent running on this same computer, and
// nowhere else. The agent still records it only while website tracking is on and you are on the clock.

const DEFAULTS = { enabled: true, port: 47113, token: '' };
const KEEPALIVE_ALARM = 'workpulse-keepalive';

async function settings() {
  const stored = await chrome.storage.local.get(DEFAULTS);
  return { ...DEFAULTS, ...stored };
}

// Only a real web page has a host we report; everything else clears the current domain.
function hostOf(url) {
  try {
    const u = new URL(url);
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return null;
    let host = u.hostname.toLowerCase().replace(/\.$/, '');
    if (host.startsWith('www.')) host = host.slice(4);
    return host || null;
  } catch {
    return null;
  }
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  return tab || null;
}

// The single place that talks to the agent. Sends { domain, incognito }; a null domain simply lets the
// agent's "fresh domain" lapse so it falls back to its own detection.
async function post(domain, incognito) {
  const cfg = await settings();
  if (!cfg.enabled) return;
  const headers = { 'Content-Type': 'application/json' };
  if (cfg.token) headers['X-WorkPulse-Token'] = cfg.token;
  try {
    await fetch(`http://127.0.0.1:${cfg.port}/domain`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ domain, incognito: Boolean(incognito) }),
    });
  } catch {
    // The agent may not be running, or website tracking may be off. Nothing to do; try again next event.
  }
}

async function reportActive() {
  const tab = await activeTab();
  if (!tab) return post(null, false);
  if (tab.incognito) return post(null, true);
  return post(hostOf(tab.url), false);
}

chrome.tabs.onActivated.addListener(() => void reportActive());
chrome.tabs.onUpdated.addListener((_id, info, tab) => {
  if ((info.url || info.status === 'complete') && tab.active) void reportActive();
});
chrome.windows.onFocusChanged.addListener((windowId) => {
  // Browser lost focus: clear the domain so time away from the browser is not attributed to the last tab.
  if (windowId === chrome.windows.WINDOW_ID_NONE) void post(null, false);
  else void reportActive();
});

// A steady reading session fires no tab events, so refresh while the browser is focused.
chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 0.25 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === KEEPALIVE_ALARM) void reportActive();
});

chrome.runtime.onStartup.addListener(() => void reportActive());
chrome.runtime.onInstalled.addListener(() => void reportActive());
