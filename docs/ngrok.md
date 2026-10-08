# External testing with ngrok

WorkPulse needs **one** ngrok tunnel, to the web app on port 8080. The web container's nginx serves the app and
forwards `/api` (REST and WebSockets) to the API inside Docker. The browser therefore talks to a single HTTPS
origin, and logins, the sign-in cookie, CSRF protection and secure WebSockets (`wss://`) all work without CORS or
code changes.

```
Internet ──HTTPS──▶ ngrok ──▶ localhost:8080  web app (nginx)
                                   │  /api/* and WebSockets (inside Docker)
                                   ▼
                              backend :8000 in Docker  (published as 127.0.0.1:8001, local only)
                                   │
                                   ▼
                              MongoDB  (127.0.0.1:27019, local only)   Redis (127.0.0.1:6379, local only)
```

The API (8001), MongoDB (27019) and Redis are bound to `127.0.0.1` in `docker-compose.yml`. They stay reachable
from your machine but are never published to the internet. Don't run `ngrok http 8001` or tunnel the database.

## One-time setup

1. Create a free account at ngrok.com and copy your authtoken.
2. Connect ngrok to your account:
   ```
   ngrok config add-authtoken <YOUR_AUTHTOKEN>
   ```

## Run it

**Terminal 1: WorkPulse**
```
cd C:\Users\osaka\Desktop\WORKPULSE
docker compose up -d
```

**Terminal 2: the tunnel**
```
ngrok http 8080
```
ngrok prints a `Forwarding` line such as `https://FRONTEND-NAME.ngrok-free.app -> http://localhost:8080`. Share
that HTTPS address with testers.

**Optional: correct links in e-mails.** Invitations, password resets and verification e-mails are built from
`FRONTEND_URL`. While testing externally, set it in `.env` to the ngrok address, then restart the API and worker:
```
FRONTEND_URL=https://FRONTEND-NAME.ngrok-free.app
```
```
docker compose up -d backend worker
```
Set it back to `http://localhost:8080` afterwards. A free ngrok address changes every time ngrok restarts; a
reserved ngrok domain keeps it stable. `CORS_ORIGINS` stays empty: the app and API share one origin.

## What testers will see

- **ngrok warning page.** On a free plan, ngrok shows a one-time "You are about to visit…" page. Click **Visit
  Site**.
- **Desktop agent.** For agents outside your network, sign the agent in with the API address
  `https://FRONTEND-NAME.ngrok-free.app/api`, using `--api-url` (see `agent/README.md`).
- **Live viewing.** Video goes peer to peer and needs a direct network path (STUN). Testers on strict corporate
  networks may need TURN (see [live-tracking.md](live-tracking.md)).

## Limitations while testing through ngrok

- **One shared address for rate limits and the audit log.** All tunnel traffic reaches nginx from the same local
  address, so every tester counts against the same limits. That includes sign-ups (20 per hour) and sign-ins
  (100 per 15 minutes). For a larger test group, temporarily set `RATE_LIMITS_ENABLED=false`, and switch it back
  afterwards.
- **Development settings.** `.env` runs in development mode (API docs on, e-mails written to the API log). For a
  hardened public deployment, use [deployment.md](deployment.md) instead of ngrok.

## Local development is unchanged

| URL | What |
|---|---|
| http://localhost:8080 | Web app |
| http://localhost:8001/api/health | API (local only), docs at http://localhost:8001/api/docs |
| `mongodb://127.0.0.1:27019` | MongoDB (local only) |
