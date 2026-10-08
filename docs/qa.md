# Full system QA (Phase 18)

Phase 18 tested every module, the infrastructure failure modes and the web app at three screen sizes. Every problem
found was fixed and the checks were run again. This page records the method, what was found, what changed and how to
repeat it.

## Scope and method

| Area | How it was tested |
|---|---|
| Modules: authentication, authorisation, employees, departments, teams, attendance (report), activity, applications, websites, screenshots, live streaming, projects, tasks, productivity, reports, notifications, AI assistant, settings | Backend test suite (pytest, real MongoDB). It runs twice: with the in-process broker and against Redis (`TEST_REDIS_URL`). |
| MongoDB unavailable, Redis unavailable | The `mongo` and `redis` containers were stopped and restarted while the stack was in use. `tests/test_resilience.py` pins the behaviour by injecting the drivers' own exceptions. |
| Duplicate requests, concurrent users, concurrent live sessions | `tests/test_concurrency.py` fires identical requests in parallel through the real application. `perf/load.py` runs 60 signed-in users and 30 live sessions against several API processes. |
| Large datasets | Seeded 100 / 500 / 1,000-employee workspaces (Phase 17, [performance.md](performance.md)). |
| Agent crash, network loss | Agent test suite: offline queue, restart recovery, stale sessions, retry on `503`. |
| Browser refresh, token expiry, network disconnect | Playwright against the Docker stack. Token expiry used an API started with `ACCESS_TOKEN_EXPIRE_MINUTES=1`. |
| Web app at desktop (1440×900), tablet (834×1112) and mobile (390×844) | Playwright sweep of all 29 app routes and the 6 public pages. Each page is checked for: <ul><li>console and page errors</li><li>failed requests</li><li>horizontal overflow</li><li>axe-core WCAG 2.1 A/AA violations, in light and dark themes</li><li>keyboard focus over 30 Tab presses</li></ul> |
| Error, loading and empty states | The same routes three more times: <ul><li>with every data request failing with a 500</li><li>with every data request held open</li><li>signed in to a brand-new empty workspace</li></ul> |

## Findings and fixes

### Backend and infrastructure

| # | Finding | Fix |
|---|---|---|
| F1 | MongoDB down: requests hung for 5 s and returned a generic 500 | `503 database_unavailable` with `Retry-After: 5`. Requests recover within about 2 s of MongoDB returning. |
| F2 | Redis down: `/health` still said "ok" | Health checks the broker (`checks.realtime`) and answers `503` when it is down. |
| F3 | Redis down: a full traceback logged on every reconnect attempt | One warning when the connection is lost, one info line when it is back. The command client has connect and read timeouts. |
| F4–F5 | Redis down: live endpoints answered 500 | `503 realtime_unavailable`. Pages that don't need realtime keep working. |
| F6 | Redis down: WebSockets dropped without a close frame | Close with `1013` (try again later). Clients reconnect. |
| F7 | Five simultaneous "start live view" requests created five sessions for one person | Partial unique index (one active session per person). The same viewer gets the existing session back; anyone else gets `409 already_live`. |
| F8 | Under load, light requests waited behind CPU-heavy productivity reports (`me/work` p95 9.2 s) | Productivity team, group and trend responses are cached for 60 s, shared through Redis. Rule, profile, employee and role changes invalidate the cache immediately. Long computations yield to other requests. The rest is capacity: p95 0.41 s with four API processes. |

### Web app

| # | Finding | Fix |
|---|---|---|
| W1 | Text contrast below 4.5:1: <ul><li>sidebar section labels, timestamps and secondary captions (`muted-foreground/80`)</li><li>status colours used as text: success 3.3, warning 2.7, destructive 4.3, info 3.4</li></ul> | Secondary text uses the full `muted-foreground`. Status tokens darkened to at least 4.6:1 on white and on their soft backgrounds. |
| W2 | Dark theme: white text on primary buttons at 3.6:1 | New `--primary-solid` token for filled controls (4.8:1). `--primary` stays bright for primary-coloured text on dark cards. |
| W3 | Progress bars had no accessible name, and `Progress` dropped the `aria-label` some pages passed | `Progress` requires and forwards `aria-label`. All bars are labelled. |
| W4 | Accessible names that didn't match the visible text: search button, profile menu, task cards, report format buttons, people picker | Names come from the visible text, with screen-reader-only additions. The picker now announces the people selected; before, a fixed label hid them. |
| W5 | Keyboard: <ul><li>the recent-activity list scrolled but couldn't be focused</li><li>tab panels took focus with no visible ring</li><li>the hidden dashboard sparklines were focusable</li></ul> | Focusable scroll region with a ring. Ring on tab panels. Sparklines no longer focusable. |
| W6 | Mobile: the productivity employee page was 104 px wider than the screen | The page grids had an implicit `auto` column that grew to fit tables. Every such grid now has a `minmax(0,1fr)` base column. |
| W7 | Offline, opening a page that wasn't loaded yet crashed to "Something went wrong" | Errors inside the app keep the sidebar and top bar. A page that fails to download says so, offers Try again, and reloads by itself when the connection returns. |
| W8 | Offline: no indication anything was wrong, and the status card still said "Operational / Connected" | "You're offline" banner. The status card shows Offline, and Unreachable when the health check fails. |
| W9 | A server error on a project page said "Project not found" | 404 shows not-found. Other errors show the error with Retry. The employee profile error also gained Try again. |
| W10 | A malformed verification link showed "Request validation failed." | "This verification link is invalid." |
| W11 | The dashboard said presence history "arrives with reports (Phase 10)" (reports shipped in Phase 13) | Accurate copy that points to Reports. |

Checked and expected, not defects:

- **Invalid invite and verification links:** the browser logs the API's 4xx, and the page shows a clear message.
- **No data loading or error state:** the sample dashboard, the upcoming Attendance page and the session-only forms (profile, appearance, security) don't load server data, so they have none.

## Results after fixes

| Check | Result |
|---|---|
| Backend tests | All pass, with the in-process broker and with Redis |
| Concurrency (`test_concurrency.py`) | One account per email; one employee per email; invitations accepted once; one live session per person |
| MongoDB / Redis outage on the Docker stack | `503` with `Retry-After`. Health reports the failing dependency. Everything recovers by itself. Realtime delivery resumes after a Redis restart. |
| Load: 60 users plus 30 live sessions, 4 API processes | 0 errors. p50 48 ms, p95 414 ms. 30/30 live sessions connected and ended cleanly. Offer→answer p50 87 ms. |
| Web sweep: 29 routes × 3 sizes, 6 public pages, light and dark | 0 axe violations, 0 overflow, 0 console errors, focus visible on every Tab stop |
| Error / loading / empty states | Every data page shows an error with Retry, a loading state, and a proper empty state in a new workspace |
| Refresh, token expiry, offline | Session and page survive a reload. Expired access tokens refresh transparently (a 401, one refresh, a retry), including the realtime socket. Offline shows a banner and recovers by itself. |

## Repeating it

- **Backend:**
  ```bash
  pytest -q
  TEST_REDIS_URL=redis://:<password>@localhost:6379/1 pytest -q
  ```
- **Load:** `python -m perf.load --api http://localhost:8200 --users 60 --live 30`. Start the API with `RATE_LIMITS_ENABLED=false` and several workers against a seeded `workpulse_perf_1000` database (see [performance.md](performance.md)). Set `JWT_SECRET` to the API's secret.
- **Web app:** run Playwright with axe-core against `http://localhost:8080`. For each route at the three sizes:
  - collect console errors and failed requests
  - compare `scrollWidth` with `clientWidth`
  - run `axe.run` with the `wcag2a`, `wcag2aa`, `wcag21a` and `wcag21aa` tags
  - Tab through the page and check each focused element has an outline or box-shadow ring

  Repeat in dark mode, with `/api` routed to 500s, with `/api` held open, and in a new workspace.
