# 36: Warm-cache re-runs still hit FastF1's rate limit

**What to build:** A Backtest re-run on a warm cache should take minutes, without FastF1 rate-limit waits. Today it doesn't, for 2022 races (and any FastF1 history), because FastF1's HTTP cache treats some saved responses as expired and re-requests them.

**Blocked by:** None (can start immediately)

**Status:** needs-triage

**Category:** bug

## Comments

**Found 2026-10-26** during the baseline re-run after tickets 29–31 and 30, on the laptop with a warm cache. For 2022 races the log shows repeated tracebacks like:

```
Request for URL https://api.jolpi.ca/ergast/f1/2022/16/results.json failed; using cached response
...
fastf1.exceptions.RateLimitExceededError: any API: 500 calls/h
```

followed eventually by `FastF1 rate limit hit while loading 2022 Italian Grand Prix …; waiting 60 min`. What's happening:

- FastF1's request cache (requests-cache) considers some cached responses stale, notably Ergast/Jolpica results, laps and qualifying, and tries to re-download them. Each attempt counts toward FastF1's 500-calls-per-hour limit.
- When the limiter blocks a re-download, requests-cache logs the traceback and serves the saved copy, so the data is unchanged. When a request has no usable saved copy, the limit propagates and ticket 17's wait kicks in.
- So results are correct, but re-runs are slow and the log is flooded. The README's statement that warm-cache runs never wait is wrong for FastF1-sourced data.

This matters before tuning, which will need many full re-runs.

Possible directions (to decide at triage): FastF1's offline mode (use only the cache, never revalidate) for re-runs, either automatically when the cache is warm or via a flag; or configuring FastF1's cache so past-season responses never expire, since finished races don't change. Either way, a missing cache entry in offline mode must surface as a clear Excluded Race reason, never as silently missing data (ticket 28's rule).

- [ ] A second full Backtest run on a warm cache makes no FastF1 network requests for data it already has, and never waits on FastF1's rate limit
- [ ] The results of that run are identical to a normal run on the same cache
- [ ] A race whose data isn't in the cache still loads normally on a normal run, and in any cache-only mode is excluded with a clear "not in cache" reason
- [ ] The requests-cache tracebacks no longer flood the output on a warm run
- [ ] The README's run-time notes are corrected
