# 60: Online warm-cache runs still re-request stale FastF1 responses

**What to build:** Decide whether online runs should stop re-requesting FastF1 responses that are already saved for finished races, so an online re-run on a warm cache doesn't spend FastF1's 500-per-hour budget or flood the log.

**Blocked by:** None

**Status:** needs-triage

**Category:** enhancement

## Background

Found while building ticket 36 (offline mode). FastF1 enables its HTTP cache with `expire_after=12h`, so an online run re-requests saved Ergast/Jolpica results, laps and qualifying responses older than 12 hours. Each one counts toward the hourly limit; when the limiter refuses, requests-cache logs a traceback and serves the saved copy. Ticket 36 avoids this with `--offline`, which serves saved responses without revalidating, but online runs still behave as the original report in ticket 36 describes. On the laptop cache (2026-10-27) an online Smoke Set opened 38 connections in 33.7 s, against 0 in 6.6 s offline, with identical output.

Options to weigh at triage:

- Leave it: `--offline` is the documented way to re-run, and online is for fetching.
- Never expire responses for finished seasons (they don't change). This touches requests-cache settings on FastF1's private cached session.
- FastF1's `ci_mode`, which reuses expired responses but also disables its parsed-data cache, making loads slower.

## Acceptance criteria

- [ ] Triage decides whether to act, and records why
