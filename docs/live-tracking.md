# Live Tracking

Live Tracking lets authorised managers see who is working and, with the employee's knowledge, view their screen in
real time. WorkPulse never routes video through its servers. The API relays only the WebRTC signalling (offers,
answers and network candidates). Video goes peer to peer from the employee's desktop agent to the manager's browser.

It runs with free STUN only. TURN, a VPS or any paid service are optional.

## Architecture

```
Manager's browser                    WorkPulse API (any process)                  Employee's desktop agent
─────────────────                    ───────────────────────────                  ────────────────────────
/live  ── GET /api/live/employees ──▶ employees + devices + presence
       ── POST /api/live/sessions ──▶ checks → live_sessions + events ─ "offer" ─▶ /api/agent/live (WebSocket)
/live/:id ⇄ WS /api/live/signaling/:id ⇄ LiveHub (relay, state machine) ⇄  agent signalling socket
     ▲                                                                              │
     └───────────────── WebRTC media (peer to peer, or via TURN when configured) ───┘
```

| Piece | Where |
|---|---|
| Page and cards | `frontend/src/features/live/live-page.tsx`, at `/live` (alias `/live-tracking`) |
| Confirmation dialog | `frontend/src/features/live/components/start-live-dialog.tsx` |
| Viewer (`LiveStreamViewer`) | `frontend/src/features/live/live-viewer-page.tsx`, at `/live/:sessionId` (alias `/live-tracking/:sessionId`) |
| WebRTC hook (`useLiveStream`) | `frontend/src/features/live/use-live-stream.ts` |
| REST endpoints | `backend/app/api/routes/live.py`, `backend/app/services/live_service.py` |
| Signalling hub | `backend/app/services/live_hub.py` (spans API processes through Redis) |
| ICE servers (`IceServerProvider`) | `backend/app/services/live_ice.py` |
| Agent side | `agent/app/live/` (signalling client and aiortc streamer) |

## Session lifecycle

**Statuses** (`live_sessions.status`):

| Status | Meaning |
|---|---|
| `requested` | Created and authorised. Waiting for the viewer's offer and the agent's answer. |
| `connecting` | Offer and answer exchanged. ICE in progress. |
| `live` | Media is flowing. |
| `interrupted` | One side or the media path dropped. It may return within `LIVE_RECONNECT_GRACE_SECONDS`. |
| `ended` | Finished. `end_reason` says why: stopped, failed, timed out, and so on. |

The response's `connection_state` gives the same information in WebRTC terms: `waiting_for_peer`, `negotiating`,
`connected`, `reconnecting`, `closed`.

**How the spec's names map to the implementation.** The spec's STOPPING and FAILED statuses aren't separate stored
states:
- Stopping is synchronous: `POST …/stop` returns the ended session.
- A failure is an `ended` session whose `end_reason` is a failure (`connect_timeout`, `connection_lost`, `agent_disconnected`, `viewer_disconnected`, `agent_error`, `capture_failed`, `server_restart`). Its timeline ends with `STREAM_FAILED`.

The spec's `manager_id` is stored as `viewer_user_id`, and `ended_reason` as `end_reason`. These names predate this
document, and the agent and web app depend on them.

**Timeline** (`live_session_events`, read with `GET /api/live/sessions/{id}/events`):

| Event | Recorded when | Actor |
|---|---|---|
| `STREAM_REQUESTED` | The viewer starts a session | Viewer, with their role |
| `STREAM_AUTHORIZED` | All checks passed (permission, scope, policy, device registered and online, work session) | Viewer |
| `STREAM_CONNECTING` | Offer and answer exchanged | Viewer |
| `STREAM_STARTED` | Media flows for the first time | Viewer |
| `STREAM_DISCONNECTED` | The agent, the viewer, the media path or the API process (deploy) dropped. `metadata.side` says which. | Agent, viewer or system |
| `STREAM_RECONNECTED` | Media flows again | Viewer |
| `STREAM_STOPPED` | Ended on purpose: viewer, time limit, policy turned off, work session ended | Viewer or system |
| `STREAM_FAILED` | Ended by a failure (see above) | System |

The security audit log (`audit_logs`) records requested, denied, connected and ended sessions as well.

**Lifecycle in practice:**
1. The manager clicks **View live**, then **Confirm & Start Stream**. Nothing starts before the confirmation.
2. `POST /api/live/sessions` validates and creates the session. It records `STREAM_REQUESTED` and `STREAM_AUTHORIZED`, and the owning API process starts its state machine.
3. The viewer page opens the signalling WebSocket. The server answers `ready` with the ICE servers.
4. The browser creates an `RTCPeerConnection` and sends an `offer`. The hub forwards it to the agent, which answers. ICE candidates go both ways.
5. The browser reports `state: connected`, and the session becomes `live` (`STREAM_STARTED`). The employee's computer shows a notification with the viewer's name.
6. **Stop Stream:**
   1. The browser sends `stop` over the WebSocket.
   2. The server ends the session (`ended`, `ended_at`, `end_reason`, `STREAM_STOPPED`) and tells the agent to stop capturing.
   3. The browser closes the peer connection and the socket, and returns to Live Tracking.

**Limits.** Sessions also end by themselves:
- at the policy's maximum length;
- if they don't connect within `LIVE_CONNECT_TIMEOUT_SECONDS`;
- if a side doesn't come back within the grace period;
- when the employee stops working.

A viewer can hold up to 4 streams at once, and an employee can be viewed by one person at a time.

## REST API

| Method and path | Purpose |
|---|---|
| `GET /api/live/employees` | People in the caller's scope with their device, online state, presence (active or idle), current application, last heartbeat, and whether they can be viewed |
| `POST /api/live/sessions` | Start a session. Body: `employee_id`, and optionally `device_id`. Company and viewer always come from the signed-in user. |
| `GET /api/live/sessions` | Session log, newest first (`employee_id`, `limit`) |
| `GET /api/live/sessions/{id}` | Current state, including `connection_state` |
| `GET /api/live/sessions/{id}/events` | The session's timeline |
| `POST /api/live/sessions/{id}/stop` | End the session. Idempotent. |
| `GET` / `PATCH /api/companies/current/live-policy` | On or off, and the maximum session length |

`POST /api/live/sessions` refuses in these cases:

| Response | When |
|---|---|
| `401` | Not signed in |
| `403` | Missing the "View live screens" permission (only Company Admins and Managers have it), or `live_view_disabled` by policy |
| `404 employee_not_found` | The employee is unknown, outside the caller's scope or in another company |
| `404 device_not_found` | The device is unknown, revoked, belongs to someone else or to another company |
| `409 agent_offline` | The device isn't connected |
| `409 not_working` | No work session is running |
| `409 already_live` | Someone else is already viewing |
| `409 too_many_streams` | The caller already has 4 streams open |

## WebSocket signalling

`WS /api/live/signaling/{session_id}`. The older path `/api/live/sessions/{session_id}/ws` is the same endpoint.

**Authentication.** The browser sends the access token as a subprotocol (`["workpulse.v1", "bearer.<token>"]`), so
it never appears in URLs or proxy logs. `?token=` is still accepted for scripts. Every connection is checked
before it is accepted:
- a valid token for an active sign-in session;
- the "View live screens" permission;
- the session belongs to the caller's company;
- the caller is the viewer who requested it;
- an API process is running the session.

Anything else closes the socket. Signed-out or revoked sessions are disconnected within `SESSION_CHECK_SECONDS`.

**Messages** (JSON, closed schemas, size- and rate-limited):

| Browser → server | Server → browser |
|---|---|
| `offer {sdp}` (START/OFFER) | `ready {status, agent_online, ice_servers, expires_at}` |
| `candidate {candidate}` (ICE_CANDIDATE) | `answer {sdp}` (ANSWER) |
| `state {state}` (CONNECTED / DISCONNECTED: `connected`, `disconnected`, `failed`) | `candidate {candidate}` |
| `stop` (STOP) | `peer_left`, then `peer_ready` (the agent dropped and came back: send a new offer) |
| `ping` (PING) | `pong` (PONG), `error {code}` (ERROR), `ended {reason, duration_seconds}` |

The agent uses `WS /api/agent/live` with its device token. It receives `offer`, `candidate`, `pause` and `stop`, and
sends `answer`, `candidate`, `state` and `ended`.

## WebRTC, STUN and optional TURN

`IceServerProvider` decides which ICE servers both peers get:

- **STUN** (`LIVE_STUN_URLS`, default `stun:stun.cloudflare.com:3478`). Free, with no account. Each side learns its public address. This is enough on the same network and through most home and office routers.
- **TURN** (`LIVE_TURN_URLS` with `LIVE_TURN_SECRET`). Optional. It relays media when a direct path is impossible: strict corporate firewalls, symmetric NAT, some mobile networks.
  - When both values are empty, peers get STUN only and nothing fails.
  - When set, each session gets short-lived credentials (TURN REST API, an HMAC of an expiry time and the user). This works with coturn's `use-auth-secret` and most hosted TURN services.
  - The production Compose file can run coturn (`--profile turn`), see [deployment.md](deployment.md).
  - Setting both URLs and secret together is required; one without the other refuses to start.

To add another TURN source later, extend `IceServerProvider`. The hub, viewer and agent need no change.

**Without TURN.** If neither direct path works, the viewer's connection fails after ICE gives up. The page shows
"Connection lost", and the session ends as `STREAM_FAILED` (`connection_lost`).

## Security

- **Server-side RBAC on every path.** REST, WebSocket and session reads need `LIVE_STREAM_VIEW`, which belongs to Company Admins and Managers. Team Leads and Employees can't start or join streams. Frontend permission checks only hide buttons.
- **Scope.** Managers can view only people in their scope (their reporting line, members of teams they lead and departments they head); admins can view the whole company.
- **Tenant isolation.** Every query is scoped by `company_id`. Another company's employees, devices and sessions all answer `404`, and its sockets are refused.
- **Trust.** `company_id` and the viewer's ID are never taken from the request body.
- **One session per person**, enforced by a unique index. A double-click is idempotent.
- Every start, denial, connection and end is in the audit log and the session timeline.

## Privacy

- **Transparent.** The employee's agent shows that monitoring is active. When a stream starts and ends, it shows a notification with the viewer's name. Streams are possible only during the employee's work session, and only when the workspace policy allows them.
- **Not recorded.** Video goes peer to peer and is never stored.
- **Never captured:** keystrokes, typed text, passwords, clipboard contents, or private message and e-mail contents. There is no hidden or stealth mode.
- **Visible to employees.** The employee-visible monitoring policy (`/privacy`) explains live viewing, who can use it and how it is logged.

## Local testing

1. `docker compose up -d --build`. `LIVE_STUN_URLS` defaults to Cloudflare's STUN, and the TURN values stay empty.
2. Sign in as a Company Admin and turn live viewing on in **Settings → Workspace → Live screen viewing**.
3. **Option A:** install and sign in the Windows agent (`agent/README.md`) as an employee, and start a work session.
4. **Option B:** use the agent's end-to-end test, which runs a real agent against your stack:
   ```bash
   cd agent
   WORKPULSE_E2E_API=http://localhost:8080/api pytest tests/test_e2e.py -k live
   ```
   It uses a synthetic frame source, never your screen.
5. Open **Live Tracking**. The person shows as online. Click **View live**, then **Confirm & Start Stream**.
6. Check `GET /api/live/sessions/{id}/events` for the timeline.

Backend tests: `pytest tests/test_live_tracking.py tests/test_live.py`. Add `TEST_REDIS_URL=…` to also run the
multi-process tests in `tests/test_scaling.py`.

## Windows agent integration

The agent side is in place.
- `agent/app/live/client.py` keeps the signalling socket. It reconnects with back-off, maps `http(s)` to `ws(s)`, and authenticates with the device token.
- `agent/app/live/streamer.py` answers offers with an `aiortc` peer connection, using the ICE servers from the offer.
- A video track encodes frames from a frame source. In production this is screen capture; tests use a synthetic source.

Natural next steps:
- multi-monitor selection;
- hardware encoding;
- an SFU route (`media_route`) for one-to-many viewing.

`live_media.py` is the extension point for that.
