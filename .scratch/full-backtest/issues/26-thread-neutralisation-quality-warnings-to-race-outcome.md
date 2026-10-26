# 26: Thread OpenF1 race-control quality warnings through to RaceOutcome

**What to build:** `openf1_loader._neutralisation_periods` already
returns `(periods, warnings)` for cases where OpenF1's
`/v1/race_control` feed is missing a VSC "ENDING" or an SC "IN THIS
LAP" event (findings' known gap). The warnings are logged at WARNING on
the module logger but are discarded by `load_weekend` — nothing on
`RaceOutcome` or `BacktestResult` records them, so a Backtest reader
doesn't see which races had an inferred cap.

Add a `quality_warnings: tuple[str, ...] = ()` field to
`RaceOutcome`, populate it from the second return value of
`_neutralisation_periods`, and surface the strings in the
`BacktestResult` for Neutralised Races where they fired. One slow test
on a race known to have a clean feed asserts empty; one hand-built
fixture with a missing ENDING event asserts the warning carries
through.

**Blocked by:** none (follow-up from ticket 22).

**Status:** needs-triage

**Category:** enhancement

Follow-up from [ticket 22](22-openf1-race-loader-and-pit-loss.md); the
derivation and the warning string are already in place, this ticket is
only about making them visible to the Backtest reader.
