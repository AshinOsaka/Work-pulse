# WorkPulse architecture

## Runtime topology

```
Browser ──► nginx (frontend container, :8080)
              ├── /            static SPA (index.html never cached, /assets immutable)
              └── /api/*       reverse proxy ──► FastAPI (backend container, :8000) ──► MongoDB
                  /api/ws      (WebSocket upgrade)
```

The SPA and API share one origin, so the refresh-token cookie can be `httpOnly` + `SameSite=Lax` with no
CORS configuration. `CORS_ORIGINS` exists for deployments that split the origins.

## Backend layout (`backend/app`)

| Package | Responsibility |
|---------|----------------|
| `core/` | Settings (pydantic-settings), logging with request IDs, error hierarchy and handlers, security primitives, Mongo lifecycle, base DI providers |
| `api/` | Routers (`routes/`) and DI wiring (`deps.py`). Routes stay thin: they validate input, call a service and shape the response |
| `auth/` | Permission and role catalogue, the `Principal`, and the `get_current_principal` / `require_permissions` / `require_roles` dependencies |
| `models/` | Persistence models (Pydantic, native `ObjectId`) |
| `schemas/` | API request and response models (string IDs) |
| `repositories/` | Data access. `TenantRepository` scopes every query by `company_id` |
| `services/` | Use cases: auth, tokens, e-mail, audit, start-up bootstrap |
| `websocket/` | Gateway endpoint, connection manager and event envelope |
| `utils/` | Small pure helpers |

**Dependency injection:** FastAPI `Depends` builds repositories and services per request from `app.state`
(settings, the Mongo client and the e-mail sender). Tests swap implementations by setting `app.state`, for
example to capture e-mails.

## Multi-tenancy

* Every tenant-owned document carries `company_id`. `TenantRepository` methods require it and inject it into
  every filter. Updates cannot rewrite `company_id`, and inserts are rejected if the entity's tenant does not
  match the scope.
* The only unscoped look-ups are explicit, named methods that need them (`find_by_email_for_auth`,
  `RefreshTokenRepository.find_by_hash`).
* E-mail addresses are globally unique, so sign-in does not need a workspace selector.

### Collections and indexes

| Collection | Key indexes |
|------------|-------------|
| `companies` | `slug` (unique), `status`, `created_at` |
| `users` | `email` (unique), `(company_id, status)`, `(company_id, role)`, `(company_id, created_at)`, `employee_id`, `created_at` |
| `roles` | `(company_id, key)` (unique; `company_id = null` for system roles) |
| `permissions` | `key` (unique) |
| `departments` / `teams` | `(company_id, name)` (unique, case-insensitive), `(company_id, head/lead)`, `(company_id, department_id)`, `(company_id, status)`, `created_at` |
| `employees` | `(company_id, status)`, `(company_id, email)` (unique), `(company_id, employee_code)` (unique, partial), `(company_id, full_name)` (case-insensitive, for sorting), `(company_id, manager_employee_id)`, `(company_id, department_id)`, `(company_id, team_id)`, `user_id`, `(company_id, created_at)` |
| `devices` | `(company_id, employee_id)`, `(company_id, status)`, `enrollment_code_hash` (unique, partial), `employee_id`, `last_seen_at`, `created_at` |
| `refresh_tokens`, `password_reset_tokens`, `email_verification_tokens`, `invitation_tokens` | `token_hash` (unique), `(company_id, user_id)`, `user_id`, **TTL** on `expires_at` |
| `audit_logs` | `(company_id, created_at)`, `(company_id, action)`, `actor_user_id` |
| `activity_segments` | `(device_id, event_id)` (unique: idempotent re-sends), `(company_id, employee_id, started_at)`, `(company_id, started_at)`, **TTL** 180 days on `created_at` |
| `activity_daily` | `(company_id, employee_id, day, app_id)` (unique: one rollup row per person, day and application) |
| `productivity_rules` | `(company_id, kind, pattern, scope, scope_id, role)` (unique) |
| `work_profiles` | `(company_id, name)` (unique, case-insensitive); employees point to one via `work_profile_id` (indexed) |
| `website_daily` | `(company_id, employee_id, day, app_id, domain)` (unique `$inc` rollup), `(company_id, day)` |
| `live_sessions` | `(company_id, employee_id, created_at)`, `(company_id, created_at)` (session log), `(company_id, status)`, `status` (startup cleanup) |
| `projects` | `(company_id, key)` (unique), `(company_id, name)` (case-insensitive), `(company_id, member_ids)`, `(company_id, status)` |
| `tasks` | `(company_id, project_id, number)` (unique: `KEY-n` references), `(company_id, project_id, status, rank)` (board order), `(company_id, assignee_ids, status)`, `(company_id, parent_id)`, `(company_id, due_date)`, `(company_id, completed_at)`, `(company_id, project_id, labels)`, `(company_id, milestone_id)` |
| `milestones` | `(company_id, project_id, due_date)` |
| `task_comments` | `(company_id, task_id, created_at)` |
| `task_activity` | `(company_id, task_id, created_at)`, `(company_id, project_id, created_at)` |
| `task_attachments` | `(company_id, task_id)` (file bytes live in encrypted object storage, not MongoDB) |
| `time_entries` | `(company_id, employee_id)` (unique, partial on `ended_at: null`: one running timer per person), `(company_id, employee_id, started_at)`, `(company_id, task_id, started_at)`, `(company_id, project_id, started_at)` |
| `notifications` | `(company_id, recipient_user_id, last_occurred_at)`, `(…, read_at)` (unread count), `(…, type, subject_key, last_occurred_at)` (throttling), **TTL** 90 days on `created_at` |
| `notification_preferences` | `(company_id, user_id)` (unique) |
| `alert_events` | `(company_id, dedupe_key)` (unique: one-time events), **TTL** 60 days |
| `report_jobs` | `(company_id, requested_by, created_at)`, `(status, created_at)` (the queue), `expires_at` (retention) |
| `screenshots` | `(device_id, client_id)` (unique: idempotent uploads), `(company_id, employee_id, captured_at)`, `(company_id, captured_at)`, `(device_id, captured_at)`, `expires_at` (retention sweeper; deliberately not TTL) |

Indexes are declared on each repository class and created idempotently at start-up (`BootstrapService`),
which also seeds the permission catalogue and the five system roles. Repositories list `obsolete_indexes`, so
an index whose options change is dropped and rebuilt automatically. The bootstrap also runs idempotent data
migrations; Phase 2 links every pre-existing user to an employee record.

## Authentication

* **Passwords:** Argon2id, rehashed on login when parameters change. A dummy verification runs for unknown
  e-mails to equalise timing.
* **Access token:** an HS-signed JWT (`sub`, `cid`, `role`, `iss`, `aud`, `exp`, `jti`), 15 minutes by
  default, held in browser memory only.
* **Refresh token:** a 384-bit opaque random value in an `httpOnly` cookie scoped to `/api/auth`, stored as a
  SHA-256 digest. Each refresh **rotates** it. Replaying a rotated token (outside a 10 s grace window for
  concurrent tabs) revokes the whole session family.
* **Session restore:** on load the SPA calls `/auth/refresh` once (single-flight, so React StrictMode and
  parallel 401s cannot double-spend a single-use token). A non-sensitive `localStorage` hint skips the call
  for visitors who never signed in.
* **Per-request user load:** suspensions and role changes take effect immediately, not when the token
  expires.
* **One-time tokens** (reset, verification) are hashed, single-use and TTL-expired. A password reset or
  change revokes all refresh tokens.

## Authorization

`app/auth/permissions.py` is the single source of truth. Roles are hierarchical; a test asserts that each
role's permissions are a superset of the role below:

| Role | Level | Permissions |
|------|-------|-------------|
| SUPER_ADMIN | 100 | all (platform scope) |
| COMPANY_ADMIN | 80 | all (within the workspace) |
| MANAGER | 60 | employee view, live/screenshot/activity view, reports view and export, task and project manage |
| TEAM_LEAD | 40 | employee view, screenshot/activity view, report view, task manage |
| EMPLOYEE | 20 | none tenant-wide; access to their own data is implicit |

Endpoints declare requirements with `Depends(require_permissions(Permission.X))`. The frontend uses the same
permission list to hide navigation and to render a *no access* state. The API is always the authority.
Custom per-company roles can later be stored in `roles` with a `company_id`.

## Row-level access scope (Phase 2)

Permissions decide *what* a role may do. `AccessScopeService` (`services/access_scope.py`) decides *which
employees* it may do it to. Every employee read is filtered by it:

| Role | Visible employees |
|------|-------------------|
| SUPER_ADMIN, COMPANY_ADMIN | everyone in the company |
| MANAGER | self, the full reporting tree (`$graphLookup` on `manager_employee_id`), members of teams they lead, employees of departments they head |
| TEAM_LEAD | self, reporting tree, members of teams they lead |
| EMPLOYEE | self only |

* An out-of-scope or foreign-tenant record returns **404, not 403**, so its existence is never disclosed.
* Scope is computed per request from live data, so a reassignment takes effect immediately.
* Writes need `EMPLOYEE_MANAGE` (admins). References in request bodies (department, team, manager, head,
  lead) are validated inside the caller's tenant, and reporting-line cycles are rejected.
* Lifecycle rules: terminating an employee deactivates their account and revokes every session. Users cannot
  change their own role or status, can assign roles only up to their own level, and the last active Company
  Admin cannot be demoted or terminated.

### Invitations

Admins create an employee with `invite=true` (or invite them later). The API creates an `invited` user with an
unusable password and e-mails a single-use, hashed, 7-day token. `POST /auth/invitations/accept` sets the
password, marks the e-mail address verified and signs the user in. Re-sending invalidates the previous link.

## Manager dashboard data layer (Phase 3)

`frontend/src/features/dashboard/data/` separates the widgets from where their data comes from:

| File | Role |
|------|------|
| `types.ts` | The contract: `DashboardDataSource`, plus KPI, trend, presence, alert and activity types |
| `live-source.ts` | Real APIs only. Head-count (`/employees`), teams, and the activity timeline (`/activity/feed`). Presence, productivity and alerts return empty values, and `availability` tells the widgets to show an empty state |
| `mock/` | **Sample data, isolated.** A fictional organisation and a seeded simulation that emits realtime events on a timer. Delete this folder once the APIs exist |
| `use-dashboard.ts` | TanStack Query hooks. A source's `subscribe()` events invalidate only the affected queries; refetches keep the previous render (no skeleton flash) |

The page has a Sample/Live switch (persisted per browser). In sample mode a banner and per-widget badges say
the data is sample, and the people are fictional, so sample activity is never attributed to real employees.
In live mode the realtime hook subscribes to the WebSocket gateway; `presence.*`, `activity.*` and `alert.*`
events map onto `DashboardEvent` once the agent emits them.

The activity feed (`GET /api/activity/feed`) is built from the audit trail. Audit events carry
`subject_employee_id`, so the feed is filtered by the caller's access scope with one indexed query. Security
events (sign-ins, failed logins) are never included.

## Desktop agent (Phase 4)

```
Agent ──register/enroll──► device secret (stored hashed server-side, DPAPI-encrypted on the device)
      ──token────────────► 30-min device JWT (aud = <api-aud>:agent, type = device)
      ──heartbeat────────► devices.last_seen_at, presence, current_session_id
      ──events (batch)───► agent_events (raw, TTL 90 days, unique per device+event id)
                            ├─ session.started/stopped ─► work_sessions + audit (feed)
                            └─ presence.changed ─────────► devices.presence (ordered by occurred_at)
```

* **Separate trust domain:** `get_current_device` (`auth/device_auth.py`) accepts only device tokens, and
  user endpoints accept only user tokens. Each request reloads the device, employee and account, so
  revocation and termination take effect immediately.
* **Idempotency and ordering:** events carry a client UUID. Re-sent batches are acknowledged as duplicates.
  Events are applied in `occurred_at` order, and stale presence updates are ignored. A lost
  `session.started` is reconstructed from the durations in `session.stopped`.
* **Honest time:** feed entries, sessions and presence use the event's own `occurred_at`, not the time it
  arrived, so events queued offline land at the right point in history. Timestamps more than 5 minutes in
  the future or more than 30 days old are rejected per event.
* **Presence:** a device is *connected* when a heartbeat arrived within `AGENT_OFFLINE_AFTER_SECONDS` and the
  agent has not reported a clean stop. Status is `active`/`idle` while connected with a running session,
  otherwise `offline`. `/api/presence` applies the same access scope as the People module.
* **Work hours:** overlaps of work sessions with daily, weekly or monthly buckets in the company timezone.
  Open sessions count up to now.

## Activity tracking (Phase 5)

```
tracker (1 sample/s, session active only)
  └─ segment closes on app/title change, idle, session end, policy change, or after 15 min
       └─ activity.segment ─► encrypted queue ─► batch (≤ max_batch_size, every sync_interval)
                                                   └─ POST /agent/events (one request per batch)
server: validate ─► policy (exclusions, titles) ─► insert_many(activity_segments, ordered=False)
                                                 └─ bulk_write($inc upserts) ─► activity_daily
```

* **Metadata only.** A segment holds the executable name, its product name, start/end, seconds with input
  and an activity level (share of seconds with keyboard/mouse input within 15 s). Input is observed only as
  *time since last input*. No keys, clipboard, screen or message contents are ever read.
* **Window titles** are off by default (`ActivityPolicy.capture_window_titles`). When enabled they are never
  read for password managers, credential prompts, messaging or e-mail clients, or private/incognito
  windows, and URLs, e-mail addresses and long numbers are redacted. The agent applies these rules before
  queuing (`agent/app/activity/privacy.py`), and the API applies them again (`backend/app/core/privacy.py`), so
  a modified agent can't store more than the policy allows.
* **Exclusions and kill switch:** excluded applications and `track_applications = false` are enforced on the
  device (not even sampled) and on the server (refused per event). The policy reaches agents on sign-in
  and every heartbeat.
* **Write path:** the agent never sends one request per event. A batch becomes one `insert_many` of new
  segments. Duplicates are detected via the unique index and skipped, so re-sends don't double count. Then
  one `bulk_write` of `$inc` upserts goes into `activity_daily`. Segments crossing local midnight (company
  timezone) are split proportionally between days.
* **Reads:** `/activity/applications` aggregates the small daily rollup (≤ 92 days, scoped by
  `AccessScopeService`). `/employees/{id}/activity?day=` reads raw segments for one day (self, or
  `ACTIVITY_VIEW` within scope). Out-of-scope requests get 404.
* **Live:** heartbeats carry the current application name (only during an active session, when tracking is
  on and the app isn't excluded), shown in the dashboard's live table.

## Screenshot monitoring (Phase 6)

```
agent: policy + active session + work hours + safe foreground app
  └─ capture (all monitors) ─► downscale ≤ 3.7 MP ─► WebP q55 (~40-250 kB) ─► AES-GCM spool on disk
       └─ POST /agent/screenshots (raw body, idempotent id) ─► re-check policy, hours, session, rate
            └─ decode/verify (Pillow, pixel cap) ─► thumbnail ─► object storage (AES-GCM) ─► metadata doc
manager: GET /screenshots (audited) ─► thumbnail URLs signed for this viewer, 5 min
         GET /screenshots/{id} (audited) ─► full-size URL ─► GET /screenshot-files/… (signature + account + scope)
```

* **Policy:** `Company.screenshot_policy` (off by default; interval 1-120 min; working hours and days in each
  employee's timezone, overnight shifts supported; retention 1-365 days). `Employee.screenshot_override`
  (`inherit` / `enabled` / `disabled`, optional interval). The agent receives the effective policy with
  every heartbeat. The server re-checks each upload: enabled, inside working hours, inside a known work
  session for that device, not stale, and at least 10 s after the previous capture.
* **Capture gating on the device:** only while the session is *active* (not idle) and within schedule. One
  capture at a random moment within each interval. Skipped entirely when the foreground app is the lock
  screen, a credential prompt, a password manager, a private/incognito window, a messaging or e-mail
  client, or an excluded app. For this check the title is read locally and never sent.
* **Storage:** image bytes never go into MongoDB documents. `core/object_storage.py` stores each object
  AES-256-GCM-encrypted (key bound as associated data) in a private volume (`object-data`) that nginx does
  not serve. The key is `STORAGE_ENCRYPTION_KEY`, or an HKDF derivation of `JWT_SECRET` under its own label.
  An S3/GCS backend implements the same three-method protocol.
* **Delivery:** `core/signed_urls.py` HMAC-signs (company, viewer, screenshot, variant, expiry). Every fetch
  re-verifies the signature, the viewer's account status and permission, and the access scope. Any failure
  is the same 404. Responses are `Cache-Control: private`, `nosniff` and `CSP: sandbox`.
* **Authorization and audit:** `SCREENSHOT_VIEW` plus `AccessScopeService` (managers see only their
  reporting line, other tenants get 404). Each gallery page logs `screenshots.listed` with the ids shown. Each
  opened screenshot logs `screenshot.viewed`. Deletions (which also need `POLICY_MANAGE`) and policy
  changes are logged too.
* **Retention:** `expires_at` is set at upload. A lifespan task (`services/retention.py`) deletes objects
  first, then metadata, so a crash never orphans a file. Changing the retention period re-dates stored
  screenshots.
* **Transparency:** `/me/monitoring` tells every person what is recorded about them right now (web
  app topbar indicator). The agent shows a red badge on the tray icon and a status row whenever a capture
  can happen.

## Live screen viewing (Phase 7)

```
Manager browser ──POST /live/sessions (audited)──────────────► LiveService: policy, scope, online, working, busy
      │◄──────────── WS /live/sessions/{id}/ws?token= ───────► LiveHub ◄── WS /agent/live (device token) ── Agent
      │   offer ─────────────────────────────────────────────────────────────────────────────────────► answer
      │   ICE candidates ◄──────────────────────────────── relayed both ways ───────────────────────────►
      └══════════════ WebRTC video (VP8, ≤1920×1080, 10 fps), peer to peer or via TURN ═══════════════════ aiortc
```

* **Signalling only:** the API never sees media. `LiveHub` (`services/live_hub.py`) holds the agents'
  persistent sockets and one socket per viewer session. It forwards only between the two parties of a
  session, using closed message schemas (`schemas/live.py`, `extra="forbid"`), size caps and a
  per-connection rate limit.
* **Authorisation:** `LIVE_STREAM_VIEW` plus the access scope (out of scope or foreign: 404). Only the
  requesting viewer can open the session's socket. Requests need: workspace live viewing enabled, the agent
  online (signalling socket open), and a running work session. One stream per employee; denied requests
  are audited (`live.session_denied`).
* **Lifecycle:** `requested → connecting → live`, with `interrupted` while a side is away, and `ended`
  with a reason. Timers: connect timeout, hard maximum (`expires_at` from the policy), and grace periods
  for a dropped viewer socket, a dropped agent socket or a lost media path. The viewer renegotiates with a
  fresh offer on recovery. Disconnect cleanup runs as its own task, so a cancelled socket handler can't skip
  it. Sessions left open by a previous process are closed at startup. Turning the policy off ends every
  stream.
* **Employee transparency:** the agent shows a Windows notification with the viewer's name at start and
  end, a red tray badge, and a status row. `/me/monitoring` and the web app indicator show who is watching.
  The agent itself refuses offers outside a work session and enforces `expires_at` locally.
* **Audit:** `live.session_requested`, `live.session_connected`, `live.session_ended` (reason, duration,
  reconnects), `live.session_denied`, `policy.live_view_updated`.
* **NAT traversal:** host candidates by default. Configure `LIVE_STUN_URLS`, `LIVE_TURN_URLS` and
  `LIVE_TURN_SECRET`; TURN credentials are minted per session with the TURN REST scheme (HMAC, expiring).
* **Media route (SFU seam):** `LiveHub` hands the viewer's offer and ICE candidates to a `MediaRoute`
  (`services/live_media.py`). Today that is `PeerToPeerRoute` (agent answers the browser directly). An SFU
  route would have the agent publish once and send each viewer's offer to the SFU instead, leaving
  authorisation, timeouts, reconnection and audit unchanged. The route is stored on every session
  (`media_route`) and sent to the viewer in `ready`.
* **Session log:** `GET /live/sessions` (newest first, optional `employee_id`, scoped like everything else) lists
  viewer, employee, device, request/connect/end times, watched seconds, reconnects, outcome and session id. The
  `live.session_ended` audit entry carries the same facts (`device_id`, `started_at`, `ended_at`).
* **Viewer resilience:** ICE `disconnected`/`failed` → fresh offer; socket drop → back-off reconnect; browser
  `offline` → reconnect attempts pause until `online`, then recover at once; a network change
  (`navigator.connection`) renegotiates immediately and is recorded as an interruption; a page refresh rejoins the
  same session within the grace period. Each state is shown to the viewer in plain words.
* **Discovery UI:** employee cards with presence and agent-connection indicators, search, department and team
  filters, and a status overview; the confirmation modal names the person (“Viewing: …”).
* **Scaling:** the viewer's socket, the agent's socket and the session's state machine can be on different API
  processes; they coordinate through Redis (see *Performance & scalability* below). Session status is persisted
  at every transition; a process that dies has its sessions ended by a cluster-wide sweeper.
* **Logs:** query-string credentials (`token=`, …) are redacted from all log records, including uvicorn's
  WebSocket lines.

## Productivity intelligence (Phase 8)

Pure calculations live in `services/productivity/engine.py` (unit-tested without a database); rule resolution
in `services/productivity/rules.py`; loading and the API in `services/productivity/service.py`.

* **Rules:** applications (executable or display name) and websites (domain, matching subdomains) are
  *productive*, *neutral* or *unproductive* at company, permission role, department, team or **work profile**
  scope. Per employee the most specific applicable rule wins (work profile > team > department > role > company); within a scope the longest matching
  domain wins. Anything uncovered is *unclassified* — reported, excluded from the productive share, and listed
  as a to-do on the Rules page. A small starter set can be loaded; rule changes are audited.
* **Websites (opt-in):** with `track_websites`, the agent reads only the host name from the active browser
  tab's address bar via UI Automation (never path, query, title or typed text; never private windows;
  exclusions apply). Browser time with a known domain follows the website rule; the rest follows the
  browser's app rule. Domains roll up into `website_daily`.
* **Time:** work time from work sessions; active/idle from the active/idle changes now stored on each
  session (`presence_changes`; older sessions are prorated from their totals); away = gaps between sessions
  within a day. Open sessions never inflate time: see `services/work_sessions.py` (ends at the device's last
  contact, or at the last recorded activity if the device moved on). The dashboard's work hours use the same rule.
* **Categories** come from the daily rollups (cheap for any range); **focus sessions** (≥25 min productive,
  interruptions ≤2 min, no unproductive >1 min) and **app switches** come from segments (ranges ≤31 days).
* **Two kinds of output, kept apart:** the *Activity score* (active ÷ work time; input only) and *Productivity
  insights* (category breakdown, *productive share* of classified time, focus, observations). Every score
  returns its formula, components and interpretation; the productive share is withheld when there is under
  30 minutes of activity or under half of it is classified. Every response carries a disclaimer that the
  figures are not a performance measure. *Task completion* and task time come from Phase 9 (below).
* **Work profiles (job roles):** Developer, Designer, Accountant, Sales, Support… — the same application means
  different things in different jobs (LinkedIn is prospecting for Sales; Figma is the work for Designers). A profile
  is created blank or from a template (`rules.PROFILE_TEMPLATES`, copied in as ordinary editable rules), and each
  employee has at most one. This is separate from permission roles. Deleting a profile removes its rules and
  releases its members. Creating, editing, membership changes and deletion are audited.
* **Further signals and scores (Phase 12):**
  * *Extended idle*: idle time in uninterrupted stretches of ≥15 minutes, from recorded active/idle changes only
    (prorated older sessions can't show stretches, so they contribute none).
  * *Focus score* = time in focus sessions ÷ productive time (needs ≥30 min productive).
  * *Work utilization* = time logged on tasks ÷ work time (needs ≥30 min work; capped at 100% with a stated
    reason when manual entries exceed recorded work). Neither expected to reach 100% nor a goal.
  * *Task completion rate* (Phase 9) and *project progress*: per project, time logged and tasks completed by the
    people in the report during the period, next to the project's overall progress.
  * A *summary* (active work, task completion, productive applications, focus time, task time, extended idle) heads
    every report; each line names the metrics it comes from. Every score returns formula, inputs and interpretation.
* **Views:** People (with department/team filters), Departments & teams (`GET /productivity/groups?by=`; sorted by
  name, never ranked), Trends (small multiples: one 0–100% panel per score plus work time on its own axis — four
  lines on one chart failed colour-vision checks — daily/weekly/monthly for everyone, a department, a team or a
  person; focus is omitted from monthly trends because it needs per-segment analysis), and each person's report
  with their own trends. Clicking any chart point, bar or day opens the data behind it (measurements, every score
  with its inputs, and the people or applications involved); every chart also has a table view.
* **Access:** team views need `ACTIVITY_VIEW` within scope; a person without it may request only their own trend
  (`employee_id` = themselves); anyone can see their own figures; rules are
  readable with `ACTIVITY_VIEW`/`POLICY_MANAGE` and editable with `POLICY_MANAGE`.

## Projects & tasks (Phase 9)

Code: `models/work.py`, `repositories/work.py`, `services/work/{access,service}.py`, `api/routes/work.py`;
frontend in `features/work`.

* **Model:** a project has a short unique key (`WEB`), members, an optional owner and due date, and a counter
  that numbers its tasks (`WEB-12`, allocated atomically with `$inc`). Tasks carry status (`TODO`,
  `IN_PROGRESS`, `BLOCKED`, `IN_REVIEW`, `COMPLETED`), priority, assignees (who must be project members), due
  date, estimate and a board `rank`; subtasks are tasks with `parent_id` (one level deep). Comment, attachment and
  time totals are denormalised on the task for cheap boards. Every change is written to `task_activity`.
* **Milestones, labels, start dates:** a milestone is a dated goal in a project (name, due date, optional
  description, can be marked reached). Top-level tasks belong to at most one milestone, which must be in the same
  project; progress = completed ÷ tasks in it. Deleting a milestone keeps its tasks. Milestones are managed by
  whoever manages the project's tasks and visible to all members. Labels are free-form, normalised to lower case
  (≤10 per task, ≤30 characters, no commas), filterable, with per-project counts for suggestions. An optional
  `start_date` (≤ due date) gives tasks a span on the timeline. Every change to these is in the task's activity.
* **Views:** Kanban (status columns, drag to change status/order), List (sortable, inline status), Timeline
  (Gantt-style bars start→due grouped by milestone, milestone flags, today line; read-only, dates are edited in the
  task panel so a stray drag can't reschedule work) and Milestones (columns per milestone; dragging only changes a
  task's milestone; mouse and keyboard). Kanban and Milestones moves are optimistic and roll back on error.
* **Access (`WorkAccess`):** `PROJECT_MANAGE` sees and manages all projects; `TASK_MANAGE` sees projects that
  include someone in the viewer's row-level scope and manages their tasks; members see their projects, create
  tasks, and edit tasks they created or are assigned to. Non-managers may only assign themselves. Anything not
  visible returns 404, not 403. Archived projects are hidden by default and accept no new tasks.
* **Board moves:** `POST /tasks/{id}/move {status, index}` re-ranks the target column (steps of 1000) and applies
  the status change through the same path as an edit, so completion timestamps, activity and timers stay
  consistent. The UI moves optimistically and rolls back on error.
* **Timer:** one running timer per employee, enforced by a unique partial index rather than application
  checks. Starting a timer stops the previous one; starting on a `TODO` task moves it to `IN_PROGRESS`;
  completing a task stops its timers. Manual time is limited to 31 days back; an entry for today ends now (never in
  the future), older ones start at 09:00 local time. Deleting a task keeps its time entries, because they are
  history.
* **Attachments:** up to 9 MB, sent as the raw request body, filename sanitised, encrypted with the same
  `ObjectStorage` as screenshots. Downloads use short-lived signed URLs bound to the viewer; the handler
  re-checks the signature, the user and the task's visibility. Only images and PDFs are served inline; everything
  else is served as a download with `nosniff` and a sandboxing CSP.
* **Dashboards:** `GET /me/work` (current task, timer, today, overdue, next 7 days, all my open tasks most urgent
  first, recently completed, counts) and `GET /work/summary` (≤92 days: completed, on-time rate, open, overdue,
  blocked, time logged, project progress, per-member workload, and the blocked and overdue tasks themselves; scoped
  like the board).
* **Productivity:** task time is split by local day into the productivity metrics. *Task completion* =
  completed ÷ (completed + open tasks whose due date has passed) for the period, shown with its formula and
  inputs and withheld when no task was due. Task time is reported next to, not inside, the Activity score.

## Alerts & notifications (Phase 14)

Code: `services/notifications/{catalog,notifier,scanner,service}.py`, `api/routes/notifications.py`; frontend
`features/notifications` (bell, centre at `/alerts`, realtime stream).

* **Types:** employee offline (agent went quiet during an open work session, not a clean shutdown, no other device
  online), device offline (not seen for 24 h), extended idle (30+ min idle in a session), shift started (first work
  session of the local day) and shift ended (a work session ended) — shifts come from desktop-agent sessions until a
  shift system exists — task overdue, project deadline (due within 2 days; critical once passed with work open), live
  session started/ended, screenshot policy changed.
* **Sources:** agent ingestion (shifts; events older than `ALERT_EVENT_FRESHNESS_SECONDS`, e.g. uploaded late from the
  offline queue, stay silent), `LiveHub` (live sessions), `ScreenshotService` (policy and per-employee changes) and
  `AlertScanner` (every `ALERT_SCAN_SECONDS`: offline, stale devices, idle, overdue tasks, deadlines; look-backs capped
  at 7 days). Sources call `Notifier.emit`, which never blocks them; `Dispatcher` does the rest in the background.
* **Recipients:** explicit users (assignees, owners), plus everyone holding the type's permission whose access scope
  includes the employee (activity alerts need `ACTIVITY_VIEW`), plus the person concerned where transparency calls
  for it (the person being viewed live; people whose screenshot setting changed). The actor is excluded.
* **Not spamming:** one-time events are de-duplicated (`alert_events`); repeats about the same subject within the
  recipient's throttle window (default 30 min, 5 min–1 day) are folded into the existing notification (count + 1,
  unread again, never re-e-mailed); beyond 30 new notifications in 10 minutes items are stored but neither pushed nor
  e-mailed; activity-style types (idle, shifts) are off by default; e-mail is opt-in for every type; only warning and
  critical items pop a toast.
* **Delivery:** stored per recipient, pushed over the realtime gateway as `notification.created` / `.updated` with the
  new unread count, and e-mailed through `EmailSender` when chosen. Slack, Teams and webhooks are listed as future
  channels; preferences are per type and channel, so they can be added without changing anyone's choices.
* **API:** `GET /notifications` (read state, type, severity, employee, time range; paged), `/unread-count`, `POST
  /notifications/mark` (ids or all matching), `GET|PUT /notifications/preferences`. People only ever see their own.

## Reports (Phase 13)

Code: `services/reports/{builders,writers,service,worker}.py`, `api/routes/reports.py`; frontend `features/reports`.

* **Types:** attendance, work hours, activity, applications, websites, screenshots (metadata only — images are never
  exported), projects, tasks, productivity and live sessions. Each builder returns typed columns and raw rows; the
  writers format them per file type. Periods: daily, weekly (Monday–Sunday), monthly or a custom range (≤366 days).
* **Filters:** people, department, team, permission role, work profile (job role) and project, where relevant.
* **Access:** `REPORT_VIEW` for the catalogue and previews (first 50 rows, ≤31 days); `REPORT_EXPORT` to generate and
  download files. Each type also needs its data permission (`ACTIVITY_VIEW`, `SCREENSHOT_VIEW`, `LIVE_STREAM_VIEW`).
  Rows only cover people in the requester's access scope and projects they can see.
* **Asynchronous generation:** `POST /reports` stores a job (*queued* — shown as "Preparing report…"); `ReportWorker`
  (started with the API) claims jobs atomically, rebuilds the requester's principal and checks their account and
  permissions again (*preparing*), builds the rows and writes the file off the event loop (*generating*), and
  marks it *ready*. Interrupted jobs are re-queued on start-up; failures keep a message safe to show. The UI polls
  every 1.5 s while a job is active.
* **Files:** CSV (UTF-8 with BOM), Excel (data sheet with filters and frozen header, plus an "About this report"
  sheet with period, filters and notes) and PDF (landscape table with repeated headings, notes and page numbers;
  DejaVu font in the image so names in most scripts render; capped at `REPORT_PDF_MAX_ROWS` with a note).
  Durations are decimal hours in CSV/Excel. Cells that a spreadsheet would treat as formulas are prefixed with an
  apostrophe (formula injection). Files are encrypted in object storage (`reports/{company}/{job}`), downloadable
  only by the requester through 5-minute signed, requester-bound URLs (`Content-Disposition: attachment`,
  `no-store`), and deleted after `REPORT_RETENTION_HOURS` (default 7 days).
* **Audit:** `report.requested`, `report.generated`, `report.failed`, `report.downloaded`, `report.deleted`.
* **Attendance caveat:** derived from desktop-agent work sessions (first start, last end, hours per day). Leave,
  holidays and shifts are not modelled yet (Phase 10), and every attendance report says so.

## AI assistant (Phase 15)

Code: `services/assistant/{tools,service}.py`, `api/routes/assistant.py`; frontend `features/assistant` (page at
`/assistant`).

* **Grounding:** Claude (`ASSISTANT_MODEL`, default `claude-opus-5-5`) never sees the database. It can only call nine
  read-only tools — live presence, team activity, project time, overdue tasks, attendance summary, recent events and
  alerts, find people, one person's summary, list projects — each a thin wrapper over the existing services. Every tool
  runs **as the person asking**: the same permission checks and `AccessScopeService` scope as the pages, so a manager's
  answers only cover their reporting line. A permission or "not found" problem goes back to Claude as a tool error,
  never as invented data. Periods are resolved server-side (today, yesterday, this/last week, last 7 days, this/last
  month, last 30 days, custom; at most 31 days, 92 for project time) in the workspace time zone.
* **Answers:** each tool returns compact facts for Claude plus **data cards** for the person (metrics, table, single-
  series chart with a table twin, list), each labelled with its period and source and linking to the page it came
  from. The system prompt requires every answer to state the period, the figures and the source, to link only to
  paths the tools returned, and to describe recorded work signals without judging character, intent, honesty, health,
  intelligence or personal circumstances.
* **Streaming:** `POST /assistant/ask` streams server-sent events: `start`, `text` (deltas), `tool`
  (running/done/error), `card`, `error`, `done`. Up to 8 tool rounds per question. Requests use adaptive thinking,
  `ASSISTANT_EFFORT` (default `medium`), prompt caching, and **server-side fallbacks** (the
  `server-side-fallback-2026-07-01` beta with `fallbacks="default"`), so an overloaded primary model can be served by a
  fallback model instead of failing.
* **History:** conversations are private to their author (`assistant_conversations`, TTL 90 days after the last
  message). The model transcript is append-only and replayed exactly as returned (thinking blocks included); the date
  and the asker's name travel in each user turn, so the system prompt and tool list stay byte-identical and cacheable.
  Refused, stopped or failed turns are shown to the person but never written into the transcript. `GET
  /assistant/conversations[/{id}]`, `DELETE /assistant/conversations[/{id}]`.
* **Access & limits:** `REPORT_VIEW` is required; `ASSISTANT_QUESTIONS_PER_HOUR` per person (default 60, counted per
  API process). Every answered question is audited (`assistant.question_answered`, with the tools used). Without
  `ANTHROPIC_API_KEY` the API reports `configured: false`, `/ask` returns 503 `assistant_not_configured`, and the page
  says so.

## Security, privacy & compliance (Phase 16)

The full audit, controls, tests and residual risks are in [security.md](security.md). In brief:

* **Sessions:** each sign-in creates an `AuthSession`. Access tokens carry its id (`sid`), and every request and every
  open WebSocket re-checks it, so signing out (this browser, remotely, everywhere, or by an admin) works at once.
* **Two-step verification:** TOTP plus recovery codes (`core/totp.py`, `services/mfa_service.py`). With it on,
  `POST /auth/login` returns a 5-minute challenge, completed at `/auth/mfa/verify`.
* **Abuse protection:** `services/throttle.py`, with counters in MongoDB that are shared across processes.
* **Browser protections:** `core/web_security.py` (Origin check, security headers), plus CSP and log hygiene in
  `frontend/nginx.conf`.
* **Audit viewer:** `GET /audit-logs` (read-only).
* **Monitoring policy:** `GET /privacy/monitoring-policy`, generated from the live settings.

## Performance & scalability (Phase 17)

Measured at 100, 500 and 1,000 employees; method, results and remaining limits are in
[performance.md](performance.md).

* **Processes:** the `backend` container runs `API_WORKERS` uvicorn processes (request handling only, background jobs
  off) and the `worker` service runs `python -m app.worker`: notification dispatch, alert scans, retention, report
  generation and productivity cache warming. Without Redis the API runs as one process doing both (development).
* **Redis (`core/broker.py`):** pub/sub for realtime events and live-viewing signalling; expiring registries (which
  process holds an agent's live socket, which runs a live session); leases so cluster-wide jobs run once; counters.
  `MemoryBroker` implements the same interface in one process.
* **No critical state only in memory:** notifications go through a durable MongoDB outbox (claimed atomically by any
  dispatcher, retried, never dropped); live sessions persist their status at every transition and are swept if their
  process dies; rate limits live in MongoDB (Phase 16).
* **Productivity cache (`productivity/day_cache.py`):** per person and day, classification, usage, focus and (once
  settled) time accounting, keyed by a fingerprint of the rules that apply. Past days are reused until late data or
  a rule change; today is recomputed every two minutes at most. Kept warm by the worker.
* **Queries:** every hot query is index-backed and bounded (no collection scans in the benchmark's profile); the agent
  authenticates with one aggregation round trip; list endpoints are paginated or capped.

## Realtime (WebSocket-ready)

* `GET /api/ws?token=<access token>` authenticates with the same `resolve_principal` as HTTP and registers
  the socket in `ConnectionManager`, keyed by company and user. Phase 1 handles `ping` → `pong`.
* Events share one envelope, `{type, payload, ts}`, with namespaces reserved for later phases: `presence.*`,
  `activity.*`, `alert.*` and `signaling.*` (WebRTC offer, answer and ICE for live screen viewing).
* Events are published to the company's channel on the broker (Redis); every API process with sockets for that
  company delivers to its own. Delivery runs in parallel with a per-socket timeout, so a slow browser never delays
  others. Open sockets re-check their sign-in session every `SESSION_CHECK_SECONDS` (Phase 16).
* The SPA keeps a single connection while signed in, with a heartbeat and exponential back-off. It refreshes
  the access token when the server closes with policy-violation code 1008.

## Frontend layout (`frontend/src`)

| Path | Responsibility |
|------|----------------|
| `app/` | Providers, router (code-split pages) |
| `components/ui/` | shadcn/ui primitives on the unified `radix-ui` package |
| `components/layout/` | App shell: sidebar, top bar, command menu (Ctrl/⌘ K), profile menu, banners |
| `components/common/` | Page header, empty states, status dots, phase badges, loaders |
| `config/modules.ts` | **Module registry**: drives navigation, the command menu, routes and the *coming soon* pages |
| `features/*` | Feature folders (auth, dashboard, settings, security, modules, errors) |
| `lib/` | API client (typed errors, single-flight refresh), query client, realtime client, formatters |
| `stores/` | Zustand: auth session (in memory) and UI preferences (persisted) |

Design tokens live in `src/index.css` as semantic CSS variables (OKLCH) with separately tuned light and dark
values. Components never use raw palette colours.

## Configuration and secrets

All configuration comes from environment variables (`backend/app/core/config.py`). The API refuses to start
without a `JWT_SECRET` of at least 32 characters. Compose passes the API only the variables it needs, so
Mongo root credentials never reach the API container. The API connects as a `readWrite` user scoped to the
WorkPulse database.

The AI assistant reads `ANTHROPIC_API_KEY` from the environment (passed through by Compose, empty by default); leave it
unset to keep the assistant switched off. Answering a question sends the tool results — names, work times, task and
project titles within the asker's scope — to the Anthropic API.
