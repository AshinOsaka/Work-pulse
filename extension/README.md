# WorkPulse Website Reporter (browser extension)

Without this extension, the WorkPulse desktop agent tries to read the active tab's address through Windows
UI Automation. That is unreliable across browsers and versions, so browser time often shows up as just
"Google Chrome" with no website. This extension reports the active tab's **domain** directly to the agent,
so time is attributed to the site (e.g. `github.com`) instead of the browser.

It is a Chromium extension (Chrome, Edge, Brave, Opera, Vivaldi).

## What it sends — and what it never sends

- **Sends:** only the host name of your active tab (`github.com`), to the WorkPulse agent on **this computer**
  over the loopback address `127.0.0.1`. Nothing goes to the internet.
- **Never sends:** the full URL, path, query string, page title, page content, form data, or anything you
  type; and it never reports **incognito / private** windows.
- The agent still records a domain only when your workspace has website tracking turned on and you are on
  the clock, and workspace app/site exclusions still apply.

This matches WorkPulse's transparency policy: no stealth tracking, no keylogging, no content capture.

## Install (load unpacked)

1. Make sure the WorkPulse desktop agent is running and signed in.
2. Open `chrome://extensions` (or `edge://extensions`), turn on **Developer mode**.
3. Click **Load unpacked** and select this `extension/` folder.
4. Open the extension's popup — it should say **Connected**.

For a managed rollout, pack/sign the extension and distribute it through your browser's enterprise policy
(force-install). The code here is the unpacked source.

## Settings

Open the extension's **Settings** (from the popup) if your agent uses a non-default configuration:

- **Agent port** — must match `extension_port` in the agent's `agent.ini` (default `47113`).
- **Pairing token** — only if the agent sets `extension_token`; otherwise leave blank.

## How it connects to the agent

The agent runs a tiny HTTP server bound to `127.0.0.1` only (never the network). The extension `POST`s
`{"domain": "github.com"}` to `/domain` on tab changes and while the browser is focused; the agent keeps the
most recent domain and uses it only while it is fresh, falling back to UI Automation if the extension is not
installed. See `agent/app/activity/extension.py`.
