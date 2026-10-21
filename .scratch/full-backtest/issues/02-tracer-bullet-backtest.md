# 02: Tracer bullet: run a Backtest over chosen seasons

**What to build:** Run a Backtest end to end with default settings. The loader can list a season's race weekends (conventional and sprint, no testing). One new public call takes a list of race weekends, a loader function and settings, and returns a Backtest Result: for each race it loads, predicts and compares with the existing `predict()` and `compare()`, unchanged. A refused race, a race whose prediction raises, and a race whose data can't be loaded each become an Excluded Race with a reason category and detail, and the run carries on. The Backtest Result holds each race's summary plus the green-race pooled headline (top-1 and top-3 Strategy Match with split tie credit, Stop Window hits over actual stops), the Neutralised-only and all-races figures, and the Excluded Races. The command gains a Backtest mode over chosen seasons that prints this with progress. Breakdowns, saving and comparison come in later tickets. Also measure how long one cold race-weekend download takes in a cloud session, and a cached load, and record both. See `../spec.md`.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] The loader lists a season's race weekends with sprints marked (slow test)
- [ ] One public call runs a Backtest over a race list with an injectable loader and returns a Backtest Result
- [ ] Each race uses only its own pre-race information; one race's outcome never changes another race's prediction
- [ ] A refused race, a race whose prediction raises and a race whose loader raises each become an Excluded Race with the right reason category, and the remaining races are still scored
- [ ] The headline is pooled over scoreable drivers in green races only; Neutralised-only and all-races figures are reported alongside
- [ ] Split tie credit carries through to every total, and every score shows numerator and denominator
- [ ] The command's Backtest mode runs chosen seasons and prints progress and the result; single-race mode is unchanged
- [ ] Cold and cached race-weekend load times are measured and recorded in this ticket
- [ ] Most tests go through the Backtest call with hand-built weekends and a fake loader
