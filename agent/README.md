# WorkPulse desktop agent (Windows)

A small background application that employees run on their work computer. It registers the device, keeps a
heartbeat with the WorkPulse API, and records **work sessions** (start/stop), **active/idle** state and, during
work sessions, **which application is in use**. A tray icon shows the employee, company, current status,
session duration, connection state, and what the workspace policy records.

## What the agent collects — and what it never does

| Collected (metadata only) | Never collected |
|---|---|
| Work session start/stop times and durations | Keystrokes or typed text |
| Active vs. idle state, from *time since last input* (`GetLastInputInfo`) | Passwords (yours is sent once at sign-in, then forgotten) |
| Heartbeat: agent online, agent version, current application name | Recordings: live video is never stored, by the agent or the server |
| Device: hostname, OS version, hashed machine fingerprint | Clipboard, files, message or e-mail contents |
| During work sessions: foreground application (executable + product name), time in it, share of seconds with input | URLs and browsing history |
| Window title, **only if the workspace enables it**, redacted, never for password managers, private browsing, messaging or e-mail | Anything outside a work session, or from excluded applications |
| Website **domain only** (e.g. `github.com`) of the active browser tab, **only if the workspace enables website tracking** — read from the address bar via Windows UI Automation | Full addresses, paths, queries, search text, private/incognito windows, excluded domains |
| Live screen video, **only if the workspace enables it**, on request of an authorised manager, during a work session, with a notification naming the viewer | Live video outside a work session, or without a notification |
| Screenshots, **only if the workspace enables them**, at the configured interval, during active work sessions and working hours | Screenshots while a password manager, credential prompt, private window, messaging or e-mail app is in front, or the screen is locked |

Enforcement is two-sided. The agent can only build the events in `app/activity/events.py`, and applies the
privacy rules in `app/activity/privacy.py` before anything is queued. The API rejects any other shape (event
schemas use `extra="forbid"`) and applies the same policy again on ingestion.

## Run it (development)

```powershell
cd agent
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt

.venv\Scripts\python -m app.main                                   # tray app (sign-in window on first run)
.venv\Scripts\python -m app.main --api-url https://your-server/api  # point at another server
.venv\Scripts\python -m app.main --headless --email you@company.com --start-session   # no UI
.venv\Scripts\python -m app.main --headless --enroll-code WP-XXXX-XXXX-XXXX           # admin-issued code
.venv\Scripts\python -m app.main --enable-autostart                # start with Windows (per user)
```

Configuration precedence: defaults → `%LOCALAPPDATA%\WorkPulse\Agent\agent.ini` → environment
(`WORKPULSE_API_URL`, `WORKPULSE_DATA_DIR`, `WORKPULSE_LOG_LEVEL`) → command line. Heartbeat, sync and idle
intervals are then set by the server policy.

## How it works

```
app/
  main.py         CLI entry point: tray (default) or headless
  agent.py        Core orchestrator used by both UIs
  config.py       Configuration loading
  auth/           Sign-in / enrolment, device secret → short-lived device tokens
  device/         Device identity (hashed MachineGuid fingerprint, OS info)
  heartbeat/      Heartbeat worker + connection state (connected / offline / revoked…)
  activity/       Work sessions, idle detection, foreground probe, activity tracker, privacy rules, event builders
  live/           Live viewing: signalling client, WebRTC streamer, screen video track
  screenshots/    Screenshot policy, capture + WebP compression, encrypted spool, scheduler and uploader
  sync/           HTTP client with retry/back-off, queue synchronisation worker
  storage/        Encrypted SQLite event queue, encrypted documents (credentials, session checkpoint)
  security/       DPAPI key protection, AES-256-GCM cipher
  ui/             Tray icon + menu (pystray), status and sign-in windows (tkinter)
  system/         Single instance, start-with-Windows, logging, worker threads
```

**Authentication.** At sign-in the agent posts the employee's email and password to `POST /agent/register`
once and receives a 256-bit **device secret**. The server stores only its SHA-256 hash. The secret is
exchanged at `POST /agent/token` for **30-minute device tokens** with their own JWT audience, so a device token
is never accepted as a user token, or the reverse. The server re-checks the device and employee on every
request: revoking the device or terminating the employee cuts access immediately, and the agent then signs
itself out and discards local data.

**Encryption at rest.** A 256-bit master key is wrapped with **Windows DPAPI** (current-user scope plus
app-specific entropy), so a copied data folder is useless on another machine or account. Credentials,
the session checkpoint and **every queued event** are encrypted with AES-256-GCM. Each record is bound
to its own context (event id), so rows can't be read, altered or swapped on disk.

**Offline first.** Every event goes into the local encrypted queue first. A background worker sends
batches oldest-first. On network or server errors it backs off exponentially (with jitter, capped at
5 minutes) and keeps the events. The first successful heartbeat after an outage releases the back-off.
Delivery is at-least-once; the server de-duplicates by event id. The queue survives restarts and is capped
at 50,000 events. A malformed event is isolated and dropped so it can never block the queue.

**Sessions.** The employee starts and stops work explicitly (tray menu or status window). Idle is reported
from when input actually stopped, and that span is re-booked from active to idle. The session is
checkpointed every 30 s. After a crash or reboot, a recent session resumes. One interrupted for more than
10 minutes (sleep, power loss) is closed at the last moment activity was observed, so time is never invented.

**Activity tracking.** While a session is active, the monitor samples the foreground window once a second
(`app/activity/foreground.py`: process image name and product description, plus the title only when the policy
allows it). Consecutive samples of the same application form a segment, which closes on a switch, idle, session
end or policy change, or after 15 minutes. Flicker under 2 s is dropped, and gaps over 5 s (sleep, hangs, a
clock set back) are never counted. Segments are queued like every other event and leave in batches with the
periodic sync, so tracking adds no requests of its own.

**Screenshots.** Off unless the workspace (or an administrator, for one employee) turns them on. The
`screenshots/` package captures all monitors once per interval, at a random moment, only while the session is
active and inside working hours. It downscales to at most ~3.7 megapixels and encodes WebP, typically
40-250 kB. Images wait in an AES-GCM-encrypted spool (capped at 500 images / 150 MB) and upload one per request
with back-off. Captures the server refuses for policy reasons are discarded; the spool is wiped on sign-out
and revocation. While captures can happen, the tray icon carries a red badge and the menu and status window
say "Screenshots: Active · every N min".

**Live viewing.** While signed in, the agent keeps a WebSocket open to `/api/agent/live` (device token,
reconnects with back-off, survives API restarts). When an authorised manager starts a stream, the viewer's
WebRTC offer arrives over it. The agent answers with its primary monitor (aiortc, VP8, at most 1920×1080,
10 fps; capture runs on its own thread) and shows a notification naming the viewer. A red tray badge and a
status row stay up while the stream runs. Streams end when the viewer stops, the session expires, work
stops, or the agent signs out. Offers outside a work session are refused.

## Test

```powershell
.venv\Scripts\python -m pytest -q                                      # unit + fake-API flow tests
$env:WORKPULSE_E2E_API="http://localhost:8080/api"; .venv\Scripts\python -m pytest -q tests/test_e2e.py
.venv\Scripts\python -m ruff check app tests; .venv\Scripts\python -m mypy app
```

## Packaging

See [docs/agent-packaging.md](../docs/agent-packaging.md). In short: `packaging/build.ps1` runs the tests,
builds a PyInstaller one-folder bundle (`dist/WorkPulseAgent/WorkPulseAgent.exe`), optionally signs it, and
optionally builds a per-user Inno Setup installer.
