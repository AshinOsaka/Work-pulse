# Performance & scalability (Phase 17)

WorkPulse was load-tested at **100, 500 and 1,000 employees**. This report covers the method, the bottlenecks found,
what changed, the results before and after, and the limits that remain. Everything can be re-run (see
[Reproducing](#reproducing)).

## Method

**Data.** `backend/perf/seed.py` builds a realistic workspace per size using the application's own models:

* departments of ~100 people and teams of ~10, with managers, team leads and reporting lines;
* one desktop agent per person, ~70% online;
* for ten working days per person: a work session with presence changes, ~32 activity segments and daily rollups;
* screenshot metadata every 10 minutes for three days;
* projects with 8 tasks per person, plus time entries, alerts and an audit trail.

| Size | Activity segments | Screenshots | Work sessions | Tasks | Daily rollups |
|---:|---:|---:|---:|---:|---:|
| 100 | 32k | 11.5k | 970 | 800 | 11k |
| 500 | 159k | 57k | 4.9k | 4,000 | 54k |
| 1,000 | 325k | 124k | 9.7k | 8,000 | 109k |

**Measurement.** `backend/perf/bench.py` runs the real application in-process (lifespan included, so indexes are
built as in production) on **one API process**, a Windows laptop, with MongoDB 8 in Docker. Three passes:

1. **Latency.** 32 endpoints, each called 3 times as admin, manager and employee (median reported), after a warm-up.
2. **Agent ingestion.** Every agent sends a heartbeat and a 20-event batch *at the same moment*. This is a
   worst-case burst; in normal use, heartbeats are spread over the 60 s interval.
3. **Alerts.** One full alert scan, then dispatching everything it raised. Then MongoDB's profiler records every
   query of one pass, to catch collection scans and wasteful plans.

Absolute numbers depend on the machine; the before/after ratios and how each number grows with size are what matter.

## Bottlenecks found (at 1,000 employees, before)

| # | Bottleneck | Symptom | Cause |
|---|---|---|---|
| 1 | Work summary | **81 s** | Quadratic Python: for each person, every task was rescanned and compared as a full model |
| 2 | Alert pipeline | **Alerts dropped** ("queue full"); 41 ms per alert | Bounded in-memory queue; recipients and scopes recomputed for every alert and user |
| 3 | Productivity analytics (team, groups, trend, reports) | **14–22 s** | All raw activity segments re-read and re-classified on every request, even for past days |
| 4 | "Last activity per open session" | Read every segment in the company (318k) to return about 700 rows | Index didn't cover `session_id` |
| 5 | Work-session overlap query | Walked each person's *entire* history | No lower bound on start time |
| 6 | Per-person task loop in productivity | 4.5 M ID comparisons per request | Quadratic look-up |
| 7 | Agent requests | 10 s median heartbeat in a burst | 5 round trips per heartbeat, plus ~14 thread-pool hops per request for trivial dependencies |
| 8 | Realtime and live viewing | Only worked within one API process | Sockets, sessions and timers lived in one process's memory |
| 9 | Web app | 1,000 cards (each with a 1 s timer) or table rows mounted; picker rendered all options and **couldn't find anyone beyond the first 200** | No virtualisation; the picker never used server search |

## What changed

**Realtime across processes (Redis).**

* `core/broker.py` handles pub/sub, expiring registries, leases and counters. `MemoryBroker` provides the same
  interface for single-process development.
* Browser events are published per company. Each API process subscribes only to companies it holds sockets for and
  delivers in parallel with a per-socket timeout.
* **Live viewing.** The viewer's socket, the agent's socket and the session's owner can each be in a different
  process. They coordinate over Redis channels and expiring registries. Stopping from any process works, and a dead
  process's sessions are ended by a sweeper that one process runs at a time (via a lease).

**No critical state only in memory.**

* Alerts go through a durable MongoDB outbox. Any dispatcher can claim a batch atomically; failed alerts are retried,
  and none are dropped.
* Rate limits are in MongoDB (Phase 16), and live-session status is persisted at every transition.

**Processes.**

* The `backend` container runs `API_WORKERS` uvicorn processes (default 2) that only serve requests.
* The new `worker` service (`python -m app.worker`) runs the background jobs: dispatch, alert scans, retention,
  reports and cache warming.
* Cluster-wide jobs hold Redis leases, so they run once even with many processes.

**Productivity cache.**

* `productivity_daily` stores, per person and day, the classified usage, focus and (once the day is settled) time
  accounting. Each entry is keyed by a fingerprint of the rules that apply to that person, so changing a rule,
  profile, team or role automatically invalidates it.
* Late uploads invalidate the past days they touch, and today's entries are recomputed every two minutes at most.
* The worker keeps the last 31 days warm, so people rarely wait for a cold computation.
* Entries are written with one bulk delete and insert per request. Upserting them one by one took 10 s.

**Queries.**

* New index `activity_segments(company_id, session_id, ended_at)`, plus a sort-then-first aggregation.
* Session overlap queries are bounded: closed sessions within 31 days, open ones via the `ended_at` index.
* The quadratic loops are replaced by keyed look-ups.
* The profiler pass at every size reports **zero collection scans**.

**Agent path.**

* Device authentication (device, employee, user status and workspace) is **one aggregation round trip**.
* Heartbeats update without re-reading the document.
* Trivial dependencies run on the event loop instead of a thread pool (`on_event_loop`).
* The agent jitters its heartbeat interval by ±10%, so agents that reconnected together after a restart don't stay
  in lockstep.

**Web app.**

* The live grid and the productivity team table are virtualised once lists reach 80 items. Table semantics, real
  `<ul>`/`<li>` lists and `aria-rowcount`/`aria-rowindex` are kept.
* The live search filters at low priority (`useDeferredValue`).
* Pickers search the server, so everyone in scope is findable, and render at most 50 rows.
* Routes were already lazy-loaded per page.

## Results

Median latency, admin role (sees everyone), one API process:

| Endpoint | 100 before → after | 500 before → after | 1,000 before → after |
|---|---:|---:|---:|
| Work summary (week) | 714 → **93 ms** | 18.6 s → **340 ms** | 80.9 s → **653 ms** |
| Productivity team (week) | 1,454 → **268 ms** | 6.8 s → **989 ms** | 18.8 s → **2.5 s** |
| Productivity groups (week) | 1,131 → **112 ms** | 5.1 s → **474 ms** | 14.1 s → **1.3 s** |
| Productivity trend (30 days) | 1,845 → **183 ms** | 9.2 s → **870 ms** | 21.0 s → **2.2 s** |
| Productivity, one person (week) | 142 → **38 ms** | 672 → **41 ms** | 1,705 → **32 ms** |
| Unclassified activity | 356 → **90 ms** | 2.5 s → **459 ms** | 6.3 s → **1.4 s** |
| Work hours (week) | 155 → **59 ms** | 1,050 → **395 ms** | 2.6 s → **839 ms** |
| Report preview: work hours (week) | 343 → **97 ms** | 2.4 s → **542 ms** | 6.5 s → **1.3 s** |
| Report preview: activity (month) | 1,772 → **262 ms** | 8.8 s → **1.1 s** | 21.7 s → **3.0 s** |
| Live employees | 30 → 21 ms | 108 → 64 ms | 259 → **95 ms** |
| Employees (page of 50) | 30 → 22 ms | 34 → 24 ms | 43 → 34 ms |

A manager's team view (about 100 people) takes 210–280 ms at every size; an employee's "My work" about 25 ms.

**Agent ingestion, 1,000 agents in one burst (heartbeat and 20 events each), one process:**

| | Before | After |
|---|---:|---:|
| Burst completed in | 20.4 s | **12.2 s** |
| Events per second | 980 | **1,645** |
| Batch upload p50 / p95 | 1,351 / 10,969 ms | **401 / 711 ms** |
| Heartbeat p50 (queued behind the burst) | 10.4 s | 5.8 s |

In steady state, 1,000 agents send about 17 heartbeats a second, a small fraction of one process's capacity.

**Alerts at 1,000 employees:** one scan takes 0.2 s and raises about 1,100 alerts. All are delivered, in 8.6 s (7.7 ms
each), down from 41 ms each with drops beyond the queue size. Same-input comparison: 2,048 alerts took 61 s before
the batching and concurrency changes, and 21 s after, producing identical notifications.

**Cold cache.** The first productivity view after a rule change, or after the cache is emptied, is slower: 13 s for a
team week at 1,000 people (that's 224,000 segments), down from 35 s in the first version of the cache. The worker
recomputes in the background so this is rarely seen.

**Browser at 1,000 employees:**

* **Live page:** lists all 1,000 people with 15–33 cards mounted, and scrolls to the end.
* **Productivity table:** `aria-rowcount` is 1,001, with 9–32 rows in the DOM.
* **Picker:** finds employee #999 by server search.
* **Phone width:** no horizontal overflow.

## Concurrency and sizing (Phase 18)

`perf/load.py` ran 60 signed-in users (admins, managers, team leads, employees) and 30 concurrent live sessions
against the 1,000-employee workspace for 45 s. Each live session had a real agent WebSocket answering the offer, so
signalling crossed Redis between processes.

| API processes | Requests/s | p50 | p95 | p99 | `me/work` p95 | Errors | Live sessions |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 (before the analytics cache) | 45 | — | 2.0 s | 9.5 s | 9.2 s | 0 | 30/30 |
| 2 | 45 | — | — | — | 2.3–3.6 s | 0 | 30/30 |
| 4 | 70.5 | 48 ms | 414 ms | 2.9 s | 590 ms | 0 | 30/30 |

Offer→answer took 87 ms p50 with 4 processes (125–132 ms with 2). Productivity team, group and trend responses are now
cached for 60 s through Redis, and edits that change them invalidate the cache immediately (see
`app/services/productivity/response_cache.py`). The remaining tail is CPU-bound analytics, which scales with
processes.

**Sizing:** run about one API process per CPU core (`API_WORKERS`), plus the background worker. For organisations
around 1,000 people with several managers using dashboards at once, use at least 4 API processes.

## Remaining limits

* **Productivity analytics at 1,000 people** take 1.3–3 s warm. That's acceptable for analytics, but larger
  organisations (5,000+) should get pre-aggregated weekly and monthly rollups next. The per-day cache is the base for
  that.
* **The team table response is 730 KB** at 1,000 people. The UI renders it efficiently, but server-side paging of
  the table is the next step for larger teams.
* **The task board** loads up to 1,000 tasks per request (716 KB for all tasks). Large boards should page per column.
* **Burst ingestion is CPU-bound** in one process (about 1,650 events/s). Scale with `API_WORKERS` or more containers,
  which now works because all shared state is in Redis or MongoDB.
* **Vendor chunk splitting was tried and reverted.** Rolldown's manual chunk grouping broke module initialisation in
  the production bundle in this Vite version, so the default splitting is kept. Every page is still its own lazy
  chunk.
* **Closed work sessions longer than 31 days** are not counted toward periods that start after that window. Open
  sessions are always counted.
* **The benchmark uses one API process and a laptop.** Production hardware and several processes will be faster.
  Docker Compose runs two API processes and a worker by default.

## Reproducing

```bash
cd backend
python -m perf.seed --employees 1000                       # workpulse_perf_1000 (password: random, in perf_meta)
python -m perf.bench --employees 1000 --json out.json      # latency, ingestion, alerts, query plans
python -m perf.probe --employees 1000 --cold productivity  # cold vs warm timings
python -m perf.queries "productivity/team"                 # MongoDB operations behind one call
python -m perf.profile_one "productivity/team"             # cProfile of one call
```

Multi-process behaviour is covered by `backend/tests/test_scaling.py` (two full application instances sharing
MongoDB and Redis; run with `TEST_REDIS_URL`), and cache and outbox correctness by `backend/tests/test_performance.py`.
