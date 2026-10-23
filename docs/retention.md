# Activity data retention ("finalise first")

WorkPulse keeps **raw** activity data only briefly, but preserves the **finalised** productivity numbers
forever, so long-horizon reports stay accurate without storing raw data indefinitely.

## What is kept, and for how long

| Data | Collection | Retention |
|---|---|---|
| Raw activity segments (per app/site time slices; source of focus & switching) | `activity_segments` | Purged **72 h** after recording (`activity_raw_retention_hours`), once the day is finalised. A 180-day TTL is a backstop only. |
| Per-day rollups (seconds per app and per website domain) | `activity_daily`, `website_daily` | Kept (no TTL) — small, and drive category and customer-time figures. |
| Work sessions (clock-in/out, presence) | `work_sessions` | Kept — drive work/active/idle time. |
| Computed per-day cache (keyed by rule fingerprint) | `productivity_daily` | 45-day TTL — a cache, safe to delete. |
| **Durable daily summaries** (finalised time, categories, focus, switching, customer time) | `daily_summaries` | **Kept forever** — the system of record for history. |

## The finaliser

The background worker runs a sweep every `activity_retention_sweep_seconds` (default hourly), cluster-safe via a
lease. For each workspace it:

1. **Finalises** the last `activity_finalize_lookback_days` settled days (default 5, to absorb late offline
   uploads) into `daily_summaries`. Today is never finalised — it is still changing.
2. **Purges** raw `activity_segments` older than `activity_raw_retention_hours`, but only for the exact
   (employee, local day) pairs that already have a finalised summary. Raw data is therefore never deleted
   before it has been summarised.

Set `activity_raw_purge_enabled=false` to keep raw data for the full backstop TTL (for example while validating
a new deployment). See `app/services/productivity/finalizer.py` and `app/services/productivity/summaries.py`.

## Reports

Trends (daily, weekly, **15-day and monthly**) read finalised days from `daily_summaries`, falling back to a
live computation for today and any day not yet finalised. Because summaries are permanent, these reports stay
correct after raw segments are purged. Standard employee/team reports (≤31 days) continue to read the rollups
and the 45-day cache, both of which the finaliser keeps populated.
