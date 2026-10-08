# WorkPulse

Workforce intelligence and employee activity management, built as a multi-tenant SaaS platform.

> **Status: Phase 9 (projects & tasks) complete.** WorkPulse has auth, multi-tenancy and RBAC (Phase 1),
> organisation management with row-level scoping (Phase 2), a manager dashboard (Phase 3), a Windows agent
> that registers devices, reports work sessions and active/idle presence, and works offline (Phase 4), and
> privacy-first application activity tracking: which application is in use and for how long, never contents
> (Phase 5), and policy-driven screenshot monitoring with private, encrypted, audited storage and a
> visible monitoring indicator for employees (Phase 6), and on-demand live screen viewing over WebRTC with
> FastAPI WebSocket signalling, confirmation, audit, timeouts and automatic reconnection (Phase 7), and a
> productivity engine with rules per company, department, team and role, separating the input-based
> Activity score from Productivity insights and showing every figure's inputs (Phase 8; extended with work profiles
> per job role, focus score, work utilization, extended idle, project signals, department and trend views), and projects & tasks with
> Kanban, list, timeline and milestone views, milestones, labels, subtasks, comments, activity, encrypted attachments, a per-employee task timer and
> manual time, employee and manager work dashboards, with task time and completion feeding the productivity
> engine (Phase 9), and reports — ten report types as CSV, Excel or PDF, generated in the background, encrypted,
> requester-only downloads and audited (Phase 13), and a realtime alert & notification engine — ten alert types,
> notification centre, WebSocket push, in-app/e-mail preferences and throttling (Phase 14), and an AI workforce
> assistant that answers managers' questions only from WorkPulse data, with sources, data cards and deep links (Phase 15;
> needs `ANTHROPIC_API_KEY`), and a security, privacy & compliance foundation: immediate session revocation, two-step
> verification, rate limiting, CSRF and CSP protections, an audit-log viewer, an employee-visible monitoring policy and
> automated tenant-isolation and access-control tests (Phase 16, see [docs/security.md](docs/security.md)).
> It is load-tested at 1,000 employees and scales out: several API processes and a background worker share realtime
> state through Redis (Phase 17, see [docs/performance.md](docs/performance.md)). A full system QA pass covered every module, infrastructure outages, concurrency and accessibility at
> desktop, tablet and mobile sizes (Phase 18, see [docs/qa.md](docs/qa.md)). It is ready for production
> deployment with HTTPS, monitoring, error tracking and backups (Phase 19, see [docs/deployment.md](docs/deployment.md)). The dashboard's live mode shows real presence, work hours and current applications.
> Attendance and timesheets arrive in a later phase (the attendance report already works from work sessions). See [docs/roadmap.md](docs/roadmap.md).

| Layer    | Stack |
|----------|-------|
| Frontend | React 19 · TypeScript · Vite · Tailwind CSS v4 · shadcn/ui (Radix) · React Router · TanStack Query · Zustand · Recharts · Lucide · Sonner |
| Backend  | Python 3.12 · FastAPI · Pydantic v2 · PyMongo (native async) · PyJWT · Argon2 |
| Data     | MongoDB 8 (auth enabled, least-privilege app user) |
| Infra    | Docker · Docker Compose · nginx (non-root) |

```
workpulse/
├── frontend/          React SPA (served by nginx, which also proxies /api and WebSockets)
├── backend/           FastAPI service (app/ core · api · auth · models · schemas · repositories · services · websocket · utils)
├── agent/             Windows desktop agent (Python, tray app) — see agent/README.md
├── docker/            Container support files (Mongo init script, Caddyfile)
├── docs/              Architecture, security, performance, QA, deployment and roadmap
├── scripts/           Backup and restore
├── docker-compose.yml       Development stack
├── docker-compose.prod.yml  Production overrides (HTTPS, hardening, TURN)
├── .env.example
└── .env.production.example
```

## Quick start (Docker)

```bash
cp .env.example .env
# Replace every CHANGE_ME value. Generate secrets with:
python -c "import secrets; print(secrets.token_urlsafe(48))"

docker compose up --build
```

For production (HTTPS, hardened containers, TURN, backups) see [docs/deployment.md](docs/deployment.md):

```bash
cp .env.production.example .env   # fill in every CHANGE_ME
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

| URL | What |
|-----|------|
| http://localhost:8080 | Web app (register a company to start) |
| http://localhost:8000/api/docs | OpenAPI docs (disabled when `ENVIRONMENT=production`) |
| http://localhost:8080/api/health | Health check, including the database |

If ports are taken on your machine, change `FRONTEND_PORT`, `API_PORT` or `MONGO_PORT` in `.env`.

**E-mail in Phase 1:** verification and password-reset e-mails go to the API log, because no mail provider exists
yet. Find the links with:

```bash
docker compose logs backend | grep "token="
```

> The Mongo init script runs only when the data volume is first created. If you change the Mongo credentials
> afterwards, recreate the volume with `docker compose down -v` (this deletes local data).

## Local development (hot reload)

```bash
# 1. Database only
docker compose up -d mongo

# 2. API  (reads ../.env; MONGODB_URL must point at localhost:${MONGO_PORT})
cd backend
python -m venv .venv && .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000

# 3. Web app  (proxies /api to VITE_API_PROXY_TARGET, default http://localhost:8000)
cd frontend
npm install
npm run dev                                          # http://localhost:5173
```

## Desktop agent

```powershell
cd agent
py -3.12 -m venv .venv; .venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m app.main --api-url http://localhost:8080/api   # tray app; sign in with your WorkPulse account
```

Details, privacy guarantees and architecture: [agent/README.md](agent/README.md). Building the installer:
[docs/agent-packaging.md](docs/agent-packaging.md).

## Quality checks

```bash
# Backend
cd backend
ruff check app tests && ruff format --check app tests
mypy app                       # strict mode
pytest -q                      # integration tests need MongoDB at MONGODB_URL; skipped if unreachable

# Containerised backend tests against the compose database
docker build --target test -t workpulse-api-test backend
docker run --rm --network workpulse_default \
  -e MONGODB_URL="mongodb://<root-user>:<root-password>@mongo:27017/?authSource=admin" workpulse-api-test

# Agent
cd agent
.venv\Scripts\python -m pytest -q          # set WORKPULSE_E2E_API to include end-to-end tests

# Frontend
cd frontend
npm run typecheck && npm run lint && npm run build
```

## API

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET  | `/api/health` | – | Readiness check with database latency (503 when degraded) |
| GET  | `/api/health/live` | – | Liveness probe |
| POST | `/api/auth/register` | – | Creates a company and its first Company Admin |
| POST | `/api/auth/login` | – | Returns an access token and sets the httpOnly refresh cookie |
| POST | `/api/auth/refresh` | cookie | Rotates the refresh token; reuse revokes the session family |
| POST | `/api/auth/logout` | cookie | Revokes the refresh token |
| GET  | `/api/auth/me` | bearer | Current user, company and effective permissions |
| POST | `/api/auth/forgot-password` | – | Always 202, which prevents account enumeration |
| POST | `/api/auth/reset-password` | – | Single-use token; signs out all sessions |
| POST | `/api/auth/verify-email` | – | Single-use token |
| POST | `/api/auth/resend-verification` | bearer | |
| POST | `/api/auth/change-password` | bearer | Signs out other sessions |
| GET  | `/api/auth/invitations/{token}` | – | Preview an invitation |
| POST | `/api/auth/invitations/accept` | – | Set a password for an invited account and sign in |
| PATCH| `/api/users/me` | bearer | Update profile name |
| GET  | `/api/users` | `USER_MANAGE` | Members, with search, role filter and pagination |
| PATCH| `/api/users/{id}/role` | `USER_MANAGE` | Assign a role (not your own; at most your level; never the last admin) |
| GET  | `/api/companies/current` | bearer | |
| PATCH| `/api/companies/current` | `POLICY_MANAGE` | Workspace profile |
| GET  | `/api/roles` | `USER_MANAGE` | Roles and the permission catalogue |
| GET  | `/api/people/summary` | `EMPLOYEE_VIEW` | Head-count overview (scoped) |
| GET  | `/api/activity/feed` | `EMPLOYEE_VIEW` | Workforce events from the audit trail, newest first; `limit`, `team_id` (scoped) |
| GET  | `/api/employees` | `EMPLOYEE_VIEW` | `search`, `status` (repeatable), `department_id`, `team_id`, `manager_id`, `sort`, `order`, `page`, `page_size` (scoped) |
| GET  | `/api/employees/options`, `/api/employees/managers` | `EMPLOYEE_VIEW` | Lightweight lists for pickers and filters |
| POST | `/api/employees` | `EMPLOYEE_MANAGE` | Create; `invite=true` also creates an account (needs `USER_MANAGE`) |
| GET  | `/api/employees/{id}` | bearer + scope | Everyone can read their own profile |
| PATCH| `/api/employees/{id}` | `EMPLOYEE_MANAGE` | Partial update; validates team/department and reporting cycles |
| POST | `/api/employees/{id}/status` | `EMPLOYEE_MANAGE` | `active`, `on_leave` or `terminated` (terminating revokes access) |
| POST | `/api/employees/{id}/invite` | `EMPLOYEE_MANAGE` + `USER_MANAGE` | Invite, or resend an invitation |
| GET/POST | `/api/employees/{id}/devices` | scope / `EMPLOYEE_MANAGE` | List devices, or register one (returns a one-time enrolment code) |
| POST | `/api/devices/{id}/revoke` | `EMPLOYEE_MANAGE` | |
| CRUD | `/api/departments`, `/api/teams` | view: `EMPLOYEE_VIEW`, write: `EMPLOYEE_MANAGE` | Delete only when empty |
| GET  | `/api/presence` | `ACTIVITY_VIEW` | Live presence of employees in scope (from agent heartbeats) |
| GET  | `/api/presence/work-hours` | `ACTIVITY_VIEW` | Hours worked per `daily`/`weekly`/`monthly` period (company timezone) |
| POST | `/api/agent/register` | – | Agent: employee sign-in → device secret (shown once) |
| POST | `/api/agent/enroll` | – | Agent: admin-issued enrolment code → device secret |
| POST | `/api/agent/token` | device secret | Agent: 30-minute device token (separate audience) |
| POST | `/api/agent/heartbeat` | device token | Online + current presence |
| POST | `/api/agent/events` | device token | Batch of session/presence events; idempotent per event id |
| WS   | `/api/ws?token=…` | bearer | Authenticated gateway (ping/pong) |

Every error uses the same shape: `{"error": {"code", "message", "details"}, "request_id"}`.

See [docs/architecture.md](docs/architecture.md) for the design.
