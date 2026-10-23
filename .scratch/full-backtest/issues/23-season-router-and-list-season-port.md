# 23: Season router: pick FastF1 or OpenF1 per season

**What to build:** A `data.load_weekend(season, event)` facade (and `list_season`) that dispatches to `openf1_loader` for season ≥ 2023 and to `fastf1_loader` otherwise, so callers stop importing either loader directly. One integration test per branch. `list_season` must give the same round/sprint-marked `RaceSpec`s from either loader (today the round number is in `RoundNumber`; via OpenF1 it is derived from meeting date order).

**Blocked by:** 22.

**Status:** needs-triage

**Category:** enhancement

Routing rule and reasoning in [`openf1-findings.md`](../openf1-findings.md). Follow-up from [ticket 18](18-check-openf1-as-second-data-source.md).

**Out of scope:** running the actual full baseline — ticket 24.
