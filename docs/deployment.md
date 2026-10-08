# Production deployment (Phase 19)

This is the guide for running WorkPulse in production with Docker Compose on one server. It covers the images, the
configuration and its safety checks, the database, observability, realtime and live viewing, backups, and upgrades.
At the end it lists what was verified against a production-configured stack before Phase 19 was signed off.

## What runs

```
Internet ──443/80──▶ caddy (TLS, HSTS) ──▶ frontend (nginx: web app, /api/ proxy) ──▶ backend (4 API processes)
                                                                                     │
         3478, 49160-49200/udp ──▶ coturn (TURN relay, optional)          worker (jobs) ─┼─▶ mongo
                                                                                     └─▶ redis
```

| Service | Image | Published | Runs as | Notes |
|---|---|---|---|---|
| caddy | `caddy:2.10-alpine` | 80, 443 (TCP+UDP) | root, only `NET_BIND_SERVICE` | Automatic HTTPS certificates. Access logs off: URLs can hold one-time links. |
| frontend | built from `frontend/` | no | uid 101 | nginx serves the built app and forwards `/api/` (REST and WebSockets). |
| backend | built from `backend/` | no | uid 999 | `API_WORKERS` uvicorn processes. Background jobs are off here. |
| worker | same image as backend | no | uid 999 | Notifications, alert scans, retention, reports, cache warming. |
| mongo | `mongo:8` | no | mongodb | Data volume `mongo-data`. |
| redis | `redis:8.2-alpine` | no | redis | Realtime fan-out between processes. Nothing persistent. |
| coturn | `coturn/coturn:4.7` | 3478, relay range | nobody | `--profile turn`. Needed when viewers and employees aren't on the same network. |

**Images.**
- The backend image is built in stages: dependencies are installed into a virtualenv in a builder stage and only that
  is copied into a slim runtime. The final image has no compilers and no pip cache.
- The web image runs the linter and type checker and builds the app in a Node stage, then ships only the static files
  on the unprivileged nginx image.
- Neither image contains `.env` files, local data or tests (`.dockerignore`).

**Container hardening** (`docker-compose.prod.yml`):
- read-only root filesystems with small `tmpfs` mounts;
- every Linux capability dropped (Caddy and coturn keep only `NET_BIND_SERVICE`);
- `no-new-privileges`;
- `restart: always`;
- rotated JSON logs (5 × 20 MB per container);
- health checks on every service.

## First deployment

1. A Linux server with Docker Engine and Compose v2.24 or later. Point a DNS name at it and open ports 80 and 443.
   For TURN, also open 3478 (UDP and TCP) and the relay range (UDP, default 49160–49200).
2. Copy the repository to the server and create the configuration:
   ```bash
   cp .env.production.example .env && chmod 600 .env
   ```
   Replace every `CHANGE_ME`; the file shows how to generate each value. Store the secrets in your password manager
   or secret store as well (see *Backups*).
3. Start:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile turn up -d     # with the TURN relay
   ```
4. Check: `docker compose ... ps` shows every service `healthy`, and `https://<DOMAIN>/api/health/ready` answers
   `"status": "ok"`. Then register the first workspace at `https://<DOMAIN>`.

Tip: put the two `-f` options in `COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml` (and
`COMPOSE_PROFILES=turn`) in the server's environment, so plain `docker compose` commands and the backup scripts use
them.

## Configuration and secrets

All configuration comes from environment variables. The repository only contains templates: `.env.example` for
development and `.env.production.example` for production. `.env` and `backups/` are git-ignored, and a test fails if a
secret-looking value appears in the web app's source or build output.

With `ENVIRONMENT=production` the API **refuses to start** while a setting is unsafe, and lists every problem at
once (`docker compose logs backend`). Configuration values are never echoed in that message.

| Refused in production | Why |
|---|---|
| `FRONTEND_URL` not `https://` | Links in e-mails, cookie security |
| `REFRESH_COOKIE_SECURE=false` | The sign-in cookie must only travel over HTTPS |
| `EMAIL_BACKEND=console` | It writes sign-in links to the log |
| `STORAGE_ENCRYPTION_KEY` unset | The screenshot key would be derived from `JWT_SECRET`, so rotating that would make screenshots unreadable |
| `REDIS_URL` unset | Several API processes need it |
| `DEBUG=true`, `CORS_ORIGINS=*` | |
| `SMTP_SECURITY=none` with a password | The password would be sent unencrypted |

Refused in every environment:
- `BACKGROUND_JOBS=false` without Redis, because worker events would never reach the API;
- TURN URLs without a TURN secret, or the reverse;
- `EMAIL_BACKEND=smtp` without `SMTP_HOST`.

**E-mail.** `EMAIL_BACKEND=smtp` delivers through any SMTP relay or provider: STARTTLS on 587, implicit TLS on 465.
When delivery fails:
- **Most actions:** they answer `503 email_unavailable` ("try again in a few minutes").
- **Password resets:** the answer stays the same as for unknown addresses, so a mail outage can't reveal which accounts exist. The failure is logged and counted in `workpulse_emails_total{outcome="failed"}`.
- **New employee invitations:** the employee and their account are kept. The admin is told to use *Resend invitation*.

## Database

**Indexes.** Each collection declares its indexes in code, and every API process applies them at start-up.
- A release that changes an index applies the change in place. A changed TTL is updated with `collMod`. Any other change rebuilds just that index.
- Before Phase 19, a changed index definition would have stopped the API from starting.
- The query and index review is in [performance.md](performance.md).

**Connection pooling.** Each API process keeps a pool of up to `MONGODB_MAX_POOL_SIZE` connections (default 50, at
least 2 kept warm). Idle connections close after 5 minutes. A request waits at most 10 s for a free connection, then
gets a retryable 503. With 4 API processes plus the worker, that is at most about 250 connections. Retryable reads and
writes are on.

**Least privilege.** The API connects as `MONGO_APP_USERNAME`, which only has `readWrite` on the WorkPulse database.
The root account is used only by the database container and the backup scripts, which run inside it.

**Data retention.** These limits are enforced by MongoDB TTL indexes and the retention job, and they are the same
numbers the employee-visible monitoring policy shows (it is generated from them):

| Data | Kept |
|---|---|
| Screenshots | Workspace policy (`retention_days`); image files and records deleted by the worker |
| Detailed activity segments | 180 days |
| Raw agent events | 90 days |
| Alerts / notifications | 90 days |
| AI assistant conversations | 90 days |
| Report files | `REPORT_RETENTION_HOURS` (default 7 days) |
| Productivity day cache | 45 days |
| Sign-in sessions, one-time links, rate-limit counters | Until they expire |
| Work sessions, daily totals, live-session log, audit trail | For the life of the workspace |

## Backups

```bash
scripts/backup.sh                    # writes backups/<UTC time>/, deletes backups older than BACKUP_KEEP_DAYS (14)
scripts/restore.sh backups/<time>    # replaces ALL data; asks for confirmation (FORCE=1 to skip)
```

**What a backup contains:**
- a gzipped `mongodump` of the WorkPulse database;
- a tarball of the object store (encrypted screenshots and report files);
- a `SHA256SUMS` file.

Both archives are checked before the backup counts.

**Restoring** checks the checksums, stops the API and worker, drops and reloads the database, replaces the files, and
starts the API and worker again.

Run backups nightly from cron or a systemd timer, and copy `backups/` off the server: another region, or object
storage with versioning.

**Keys are not in the backup.** Screenshots are restorable only with the same `STORAGE_ENCRYPTION_KEY`, and existing
sessions need the same `JWT_SECRET`. Keep both in your secret store, separately from the backups.

On a single MongoDB server the dump is consistent per collection, not across collections. For a strict
point-in-time copy, run MongoDB as a replica set and add `--oplog`, or use storage snapshots.

## Observability

**Health probes:**

| Endpoint | Meaning |
|---|---|
| `GET /api/health/live` | Liveness: the process answers. No dependency checks. Used by Docker. |
| `GET /api/health/ready` (= `/api/health`) | Readiness: MongoDB and Redis reachable. `503` with the failing check otherwise. |
| `python -m app.worker --check` | Worker health: its heartbeat is fresher than 60 s (jobs running, event loop responsive) |

**Structured logs.**
- With `LOG_JSON=true` (the production default), every line is a JSON object with `ts`, `level`, `logger`, `message` and `request_id`.
- Request lines add `http_method`, `http_path`, `http_route`, `http_status` and `duration_ms`.
- Responses carry `X-Request-ID`, including the 500 answer to an unexpected error, so a user can quote it.
- Query strings, tokens and passwords are never logged.

**Metrics** (Prometheus). The API serves `GET /metrics` outside `/api`, so the public proxy never exposes it. Scrape
`backend:8000/metrics` from inside the Docker network, with `Authorization: Bearer <METRICS_TOKEN>` when that is set.
The values from all API processes are combined. The worker serves its metrics on `worker:9101`.

| Metric | |
|---|---|
| `workpulse_http_requests_total{method,route,status}` | Requests, by route template (no IDs in labels) |
| `workpulse_http_request_duration_seconds{method,route}` | Latency histogram |
| `workpulse_websocket_connections{channel}` | Open sockets: `app`, `agent_live`, `live_viewer` |
| `workpulse_websocket_sessions_total{channel}` | Sockets accepted |
| `workpulse_errors_total{component}` | Errors logged, by component (e.g. a failing background job) |
| `workpulse_client_errors_total{kind}` | Errors reported by browsers |
| `workpulse_emails_total{backend,outcome}` | E-mail delivery |
| `workpulse_build_info{version,environment}` | Running version |

Suggested alerts:
- readiness not ok;
- worker unhealthy;
- 5xx rate above 1%;
- p95 latency above 2 s;
- `workpulse_errors_total` rising;
- `workpulse_emails_total{outcome="failed"}` above zero.

**Error tracking.** Every error logged with an exception reaches the registered error reporters exactly once:
unhandled request errors, background job failures and WebSocket errors. So do browser errors (uncaught errors,
unhandled promise rejections, and the errors behind the error pages), which the web app posts to
`POST /api/client-errors`. That endpoint is rate-limited, size-limited, and given page paths only, never query
strings.

Set `SENTRY_DSN` to send all of these to Sentry. Request bodies, cookies and headers are never attached. Another
tracker plugs in with `register_error_reporter()` in `app/core/observability.py`.

## Realtime (WebSockets)

The route is Caddy (TLS) → nginx (`/api/`, upgrade headers, 1-hour read timeout) → any API process. Events cross
processes through Redis, so a browser's socket and the process raising an event (or the worker) don't need to be the
same.

**Redeploys.** nginx looks up the API's address through Docker's DNS (`DNS_RESOLVER`, valid 10 s) rather than once at
start-up. A redeployed API container gets a new address, and the old behaviour returned 502 until nginx restarted.

**Authentication.**
- **Browsers** send the access token as a WebSocket subprotocol (`bearer.<token>`), so it never appears in a URL or a proxy log.
- **Agents** use an `Authorization` header.
- **All sockets:** the `Origin` is checked, and a revoked session closes the socket within `SESSION_CHECK_SECONDS`. When Redis is down, sockets close with `1013` (try again later) and clients reconnect with back-off.

**Client address.** Only the address in `TRUSTED_PROXY` (Caddy's fixed address on the `edge` network) may tell nginx the
client's address and scheme. Rate limits and the audit trail therefore record the address Caddy saw, and a client
can't spoof it with its own `X-Forwarded-For`.

## Live viewing (WebRTC)

The API only relays signalling. Video goes peer to peer, or through TURN.

- **STUN/TURN.** Set `LIVE_STUN_URLS`, `LIVE_TURN_URLS` and `LIVE_TURN_SECRET`, and run coturn (`--profile turn`) with
  the same secret and `TURN_EXTERNAL_IP` set to the server's public address.
  - Each session gets TURN credentials that expire after `LIVE_TURN_TTL_SECONDS`. They are an HMAC of an expiry time and the user, so coturn checks them without a user database.
  - The relay refuses to forward to private and link-local address ranges by default (`TURN_PEER_RULES`), so it can't be used to reach the internal network.
- **Secure signalling.** Everything goes over WSS. Only the viewer who requested a session may join it. Messages follow
  closed schemas and are size- and rate-limited. The agent socket authenticates with its device token.
- **Recovery.**
  - If either side drops, the session waits `LIVE_RECONNECT_GRACE_SECONDS` and the viewer renegotiates.
  - If the media path fails, the viewer restarts ICE.
  - **Since Phase 19, sessions survive API restarts and deploys.** A process that shuts down hands its sessions over instead of ending them. Video keeps flowing meanwhile. Whichever process the viewer and agent reconnect to adopts the session (one process wins, using a Redis lease), and the duration carries on.
  - A session nobody returns to ends after the grace period. A crashed process's sessions end once its registry entry expires.

## Upgrading

```bash
git pull
scripts/backup.sh
docker compose up -d --build backend worker frontend
```

- Index changes apply themselves.
- Live sessions are handed over.
- Browsers and agents reconnect by themselves.
- A browser holding an old version of the app reloads the page when it opens a page whose files changed.

Watch `docker compose ps` until everything is `healthy`.

## Verified before sign-off

These checks ran against the production configuration on a local machine:
- `docker-compose.yml` plus `docker-compose.prod.yml`;
- Caddy with its local certificate authority for `localhost`;
- 4 API processes, the worker, MongoDB, Redis and coturn;
- a Mailpit SMTP sink in place of a real mail provider.

| Check | Result |
|---|---|
| Frontend production build (lint, type check, build inside the image) | Built; served over HTTPS with HSTS and CSP; assets cached immutably |
| Backend start-up | All services healthy; an unsafe setting (console e-mail) refused with a clear message |
| MongoDB / Redis | Readiness ok; least-privilege app user; pools configured |
| Authentication | Register; e-mail verification, password reset and invitation e-mails delivered over SMTP and redeemed; refresh rotation; `Secure` cookie; logout; no account enumeration |
| REST APIs | Departments, employees, projects, tasks, productivity, monitoring policy, audit log; report generated by the worker and downloaded |
| WebSocket | WSS through Caddy and nginx; subprotocol authentication; invalid token and foreign Origin refused; notification pushed from the worker through Redis to another process's socket |
| WebRTC | Agent: live view end-to-end over WSS. Browser: relay-only via coturn with API-minted credentials, video playing; a wrong credential refused; video uninterrupted and the session live again after an API restart |
| Screenshot storage | Agent upload; signed URLs; files encrypted at rest; restored screenshots decrypt |
| Agent synchronisation | Agent end-to-end suite against `https://…/api` (sign-in, heartbeats, event sync, screenshots, live view) |
| Backups | Backup, change, restore: database and files identical to the backup; the later change gone |
| Logs | JSON; no secrets, tokens or one-time links in any container's logs |
| Exposure | Only 80/443 (and TURN) published; `/metrics` and API docs not reachable from outside; containers read-only and non-root |
