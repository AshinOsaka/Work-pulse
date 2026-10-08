# Security, privacy & compliance (Phase 16)

This is the Phase 16 security audit of WorkPulse. For each requirement it records what is in place, the
automated tests that prove it, what the audit found and fixed, and the risks that remain. The tests run in the normal
suites (`backend/tests`, `agent/tests`). If a change breaks one of these guarantees, a test fails.

**Audited:** the API (149 HTTP routes and 3 WebSockets), the web app, the nginx front end, Docker Compose and the
Windows agent.

## Findings fixed in this phase

| # | Finding | Severity | Fix |
|---|---------|----------|-----|
| 1 | Access tokens stayed valid for up to 15 min after sign-out, password change or token-theft detection. Nothing tied a token to a server-side session. | High | Server-side sessions (`auth_sessions`). Each access token carries `sid`, and every request checks that the session is still active. |
| 2 | Open WebSockets (realtime and live viewing) were authorised once and kept running after sign-out or suspension. | High | `session_guard` re-checks the session and the account every 15 s (`SESSION_CHECK_SECONDS`). It closes the socket with code 4401, which ends any live stream. The web app then signs out. |
| 3 | No rate limiting on sign-in, registration, password reset, invitation/verification links or agent sign-in. | High | Fixed-window limits stored in MongoDB, so they are shared by every API process. Responses are 429 with `Retry-After`. Failures per account are limited to 10 per 15 min, which stops brute force even from many IPs. |
| 4 | The client IP could be spoofed. nginx *appended* to a client-supplied `X-Forwarded-For` and uvicorn trusted every hop, so attackers could pick the IP used for limits and the audit trail. | Medium | nginx now *replaces* `X-Forwarded-For` with `$remote_addr`. |
| 5 | Secrets reached nginx logs. The default log format records query strings (`/api/ws?token=…`, signed-URL signatures) and the `Referer` header (`/reset-password?token=…`). | Medium | A custom log format with no query strings and no referrer. `Referrer-Policy: no-referrer`. |
| 6 | No Content-Security-Policy, and the theme script was inline. | Medium | Strict CSP (`script-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`, …). The theme script moved to `/theme-init.js`. A browser walk through every page shows no violations. |
| 7 | No CSRF defence beyond `SameSite=Lax` on the refresh cookie. A cross-site page could sign users out, mint tokens or open WebSockets. | Medium | `BrowserSecurityMiddleware` refuses any state-changing request or WebSocket handshake whose `Origin` is not WorkPulse's own. Agents and scripts send no Origin and are unaffected. |
| 8 | Attachments were shown inline based on the client-declared type. | Low | Inline types (images, PDF) must match the file's magic bytes. Anything else is stored and served as an opaque download, still sandboxed and `nosniff`. |
| 9 | Sign-out wasn't audited. The audit trail had no viewer. | Low | `auth.logout` and session/MFA events are now recorded. The audit-log viewer is read-only, for `AUDIT_LOG_VIEW` holders. |
| 10 | No second factor. | — | TOTP two-step verification with recovery codes. Sign-in becomes two steps and the agent requires an enrolment code when MFA is on (details below). |
| 11 | No employee-visible monitoring policy. The monitoring popover also over-promised: it said nothing is recorded while a password manager is in front, but only the window *title* is withheld. | — | `/privacy` page built from the live settings. The popover wording is corrected. |
| 12 | API responses had no security headers and could be cached. | Low | `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, COOP/CORP, `default-src 'none'` CSP and `Cache-Control: no-store` unless a route sets its own. |

## Authentication

| Control | Implementation | Tests |
|---------|----------------|-------|
| JWT | HS256 with a ≥ 32-character secret (startup refuses weaker). Issuer, audience and type are required, with 10 s leeway. Each token carries `sid`, user, company and role. Agent and MFA-challenge tokens have their own audiences and can't be used as access tokens. | `test_security.py`, `test_hardening.py::test_forged_tampered_and_foreign_tokens_are_rejected` (alg none, wrong key, missing or unknown session, other company, expired) |
| Refresh tokens | Opaque 384-bit values in an httpOnly `SameSite=Lax` cookie scoped to `/api/auth`, `Secure` by default. Only SHA-256 digests are stored. | `test_refresh_cookie_is_locked_down`, `test_secrets_are_stored_only_as_hashes` |
| Rotation | Single use. Reusing a rotated token outside the 10 s concurrent-tab grace revokes the whole session (theft response). | `test_auth.py::test_refresh_rotation_and_reuse_detection` |
| Password hashing | Argon2id, rehashed on sign-in when parameters change. Unknown accounts take the same time to fail (no enumeration). | `test_secrets_are_stored_only_as_hashes` |
| MFA foundation | RFC 6238 TOTP, matching the RFC test vectors. ±1 step drift is allowed. Replay is refused (compare-and-set on the last step). Secrets are AES-GCM encrypted and bound to the user. There are 10 single-use recovery codes, stored hashed. Setup, turn-off and code regeneration require the password and a code. Admins can reset MFA (audited). | `test_sessions_mfa.py` (7 tests) |
| Session revocation | Sign out this browser, one remote session, or all others. Password change and password reset end all other sessions. Admins can sign a person out everywhere. Suspension and deactivation take effect on the next request. | `test_sessions_mfa.py`, `test_realtime_and_live_sockets_close_when_the_session_ends` |

## Authorization

Roles carry fixed permission sets (`app/auth/permissions.py`). Row-level scope (`AccessScopeService`) limits managers and
team leads to their reporting line. Out-of-scope records answer *404*, never *403*, so their existence isn't
disclosed.

| Surface | Enforcement | Tests |
|---------|-------------|-------|
| API | Route dependencies (`require_permissions`) plus service checks and scope | `test_rbac_matrix.py::test_permission_matrix`: 21 endpoints × 4 roles, with expectations derived from the role catalogue |
| WebSocket | Token at handshake, Origin check, session re-check | `test_tenancy_and_ws.py`, `test_cross_site_requests_are_refused` |
| WebRTC | Session creation needs `LIVE_STREAM_VIEW` + scope + workspace policy. Only the requesting viewer may join the signalling socket. The employee is notified. Sessions time out. | `test_live.py`, `test_live_signalling_requires_the_permission_and_the_requesting_viewer` |
| Screenshots | `SCREENSHOT_VIEW` + scope. Files are reached only through signed, viewer-bound, expiring URLs that are re-authorised on use. | `test_screenshots.py`, `test_signed_links_are_bound_to_tenant_and_viewer` |
| Reports | `REPORT_VIEW` to list, `REPORT_EXPORT` to generate. Permissions are re-checked before generation. Downloads go only to the requester. | `test_reports.py` |
| Employees / projects | `EMPLOYEE_*`, `PROJECT_MANAGE` / `TASK_MANAGE` + membership + scope | `test_rbac_matrix.py`, `test_work.py`, `test_organization.py` |

## Tenant isolation

`TenantRepository` adds `company_id` to every query. On top of that, `test_tenant_isolation.py` tests isolation
end to end:

* **Every id route.** Company A's admin calls each of the 55 route/method pairs that take an id, using Company B's real
  ids and valid bodies. None succeeds or leaks B's canary string, and B's data is unchanged afterwards. The routes are
  enumerated from the app, so **new endpoints are covered automatically**.
* **Every list endpoint.** No GET endpoint returns B's canary or ids, including with B-specific filters.
* **Signed links.** Changing the company, user, expiry or signature fails, and so does re-signing for A's own identity.
* **Live sessions and the realtime gateway.** A can't see, stop, start or join B's session. Events broadcast to B
  never reach A's socket.

## Audit log

Recorded with actor, subject employee, IP address, browser and metadata:

* **Sign-in and sessions:** sign-in (with the second factor used), sign-out, failed sign-in, MFA changes and
  failures, session revocations, password events.
* **Monitoring access:** screenshot views and browsing, screenshot deletion, live view requested, started, refused and
  ended.
* **Reports:** requested, generated, downloaded (export), deleted.
* **Roles and account access:** role changes, admin sign-out of someone everywhere, MFA reset.
* **Policies:** activity, screenshot (workspace and per person), live view, productivity rules and work profiles.
* **People and organisation:** employees, departments, teams, workspace settings.
* **Devices, projects and the AI assistant.**

Admins browse it at **Security → Audit log**, filtered by type, person and dates. There is no API to edit or delete
entries. Metadata keys that look like credentials are never shown. Tests: `test_required_events_are_audited_and_readable_by_admins_only`.

## Privacy

* **Monitoring & privacy page (`/privacy`).** Visible to every member and generated from the current settings. For
  each kind of data it says what is collected, when, why, how long it's kept, who can see it (role and scope), and
  the safeguards. For screenshots it uses the person's own effective setting. It also lists what is never
  collected and the administrators to contact. Test: `test_monitoring_policy_is_visible_to_employees_and_follows_settings`.
* **Never collected.**
  * Keystrokes and typed text, passwords, clipboard, audio and video.
  * Window titles of password managers, messaging, e-mail and private windows.
  * Full URLs.
  * Anything while the person is idle or signed out.

  The agent contains no keyboard hooks, key-state, clipboard or media APIs and imports no such libraries
  (`agent/tests/test_privacy_guarantees.py`). Idle detection reads only the *time* of the last input. The API
  rejects unknown fields in agent events (`test_agents_cannot_send_keystrokes_or_extra_fields`).

## Hardening checklist

| Item | Status |
|------|--------|
| CORS | Off by default (same-origin deployment). `CORS_ORIGINS` allows exact origins only. Test: `test_cors_admits_only_configured_origins` |
| CSRF | Origin check on state-changing requests and WebSockets, plus `SameSite=Lax` and a path-scoped refresh cookie. Bearer tokens aren't sent automatically by browsers. Test: `test_cross_site_requests_are_refused` |
| Rate limiting | See finding 3. Tests: `test_sign_in_is_throttled_per_account`, `test_reset_links_agent_sign_in_and_invitation_tokens_are_throttled`. Live signalling and the AI assistant have their own limits. |
| Input validation | Pydantic models with length limits. Agent payloads forbid extra fields. Ids are parsed strictly. Search is literal (no regex injection). Validation errors never echo input. Test: `test_malformed_input_never_causes_a_server_error` sends junk ids and Mongo operators to every route; none returns 5xx. |
| File validation | Screenshots are decoded and re-encoded server-side (images only). Attachments: 9 MB limit, empty files refused, safe filenames, magic-byte check for inline types, sandboxed downloads. Test: `test_uploaded_files_are_checked_not_trusted` |
| No secrets in frontend | The only build-time variable is `VITE_API_BASE_URL`. Test: `test_frontend_ships_no_secrets` scans `src`, `public` and `dist` for keys, private keys and connection strings. |
| No sensitive logging | Query strings are never logged by the API or nginx. A redaction filter covers tokens and passwords. Test: `test_credentials_never_reach_the_logs` captures every log record during registration, sign-in, refresh, password reset and a WebSocket connection. |
| Secure cookies and tokens | httpOnly, `Secure` by default, `SameSite=Lax`, path-scoped. Access tokens live only in memory. |
| Signed storage URLs | HMAC under a purpose-specific key. Bound to company, user, object and variant. Short-lived (`SCREENSHOT_URL_TTL_SECONDS`). Re-authorised on use. Objects are AES-GCM encrypted at rest. |

## Residual risks and deployment notes

* **TLS** is expected at the edge. Behind HTTPS, add `Strict-Transport-Security` (see `frontend/nginx.conf`) and keep
  `REFRESH_COOKIE_SECURE=true`.
* **Another proxy in front of nginx.** Set `TRUSTED_PROXY` on the web container to that proxy's address: only it may
  report the client address and scheme (the production Compose file does this for Caddy, see
  [deployment.md](deployment.md)). The API is never published on the host in production; if it is ever exposed
  directly, narrow `--forwarded-allow-ips` instead of `*`.
* **WebSocket authentication (Phase 19).** Browsers can't set headers on WebSockets. The web app sends the access token
  as a subprotocol (`bearer.<token>`, answered with `workpulse.v1`), so it never appears in URLs: nginx's *error* log
  records full request lines when an upstream fails, which is how tokens reached logs before. `?token=` is still
  accepted for older clients. The agent uses an `Authorization` header.
* **Signed file links** stay valid until they expire (default 5 min), even if the viewer signs out in the meantime.
* **Inline styles.** The CSP allows `'unsafe-inline'` for *styles only*, because component libraries set style
  attributes. Scripts are strict.
* **MFA enforcement** per workspace (e.g. "required for admins") is not built yet; the foundation is in place.
* **Retention.** Work sessions, daily summaries, the live session log and the audit trail are kept for the life of
  the workspace. The privacy page says so. Configurable retention for these is a candidate for a later phase.
* **Rotating `JWT_SECRET`** ends every session. Two-step secrets survive it only when `STORAGE_ENCRYPTION_KEY` is set
  (recommended in production).
