# 06: Comparing predictions with the actual race

**What to build:** A second public call takes the Strategy Predictions plus the race's actual Stints and neutralisation periods and reports how the predictions did. Actual Strategies are extracted from race Stints. Per driver: whether the actual Strategy was the top pick, whether it was in the top 3 (Strategy Match on stop count and Compound sequence only), and whether each actual stop fell inside its predicted Stop Window (scored separately). The race is flagged as a Neutralised Race if it had a Safety Car or VSC. Drivers who retired or never completed a stop are marked unscoreable. A race summary gives counts of top-1 matches, top-3 matches and Stop Window hits.

**Blocked by:** 05 (Plausible pruning and Stop Windows)

**Status:** done

- [x] Each driver's actual Strategy is extracted correctly from their race Stints
- [x] Top-1 and top-3 Strategy Match are reported per driver
- [x] A stop two laps outside the window still counts as a Strategy Match if stop count and Compounds match
- [x] Stop Window hits are reported per stop, independently of Strategy Match
- [x] A race with any Safety Car or VSC period is flagged as a Neutralised Race
- [x] Retired drivers and drivers who never stopped are unscoreable and excluded from the summary counts
- [x] A race summary reports top-1, top-3 and Stop Window hit counts out of scoreable drivers
- [x] Tests use hand-built predictions and actual Stints through the public calls

## Comments

**From ticket 01 (2026-10-19).** The race weekend description's `Stint` has driver, Compound, start lap and end lap, and `NeutralisationPeriod` has kind and laps. There is no finishing status, so "retired" can only be inferred from a last Stint ending before `PreRaceInfo.race_laps`. That misses lapped finishers (who end on fewer laps without retiring). Consider adding a finishing status to `RaceOutcome`, populated by the loader in 07.

**From ticket 05 (2026-10-19).** Each `PlannedStop` carries `first_lap`, `best_lap` and `last_lap`. Because the other stops are re-optimised when one stop moves, consecutive Stop Windows of a multi-stop Strategy can overlap (e.g. H → S → H: laps 19–29 and 28–38). Score the n-th actual stop against the n-th predicted Stop Window, not against whichever window contains the lap. Predictions now contain only Plausible Candidate Strategies, so a driver's actual Strategy may be absent from their prediction; that should count as neither top-1 nor top-3.

## Implementation notes

**What was built.** A second public call `compare(predictions, weekend) -> RaceComparison` lives in `src/f1_strategy/scorer.py` and is re-exported from `f1_strategy`. It extracts each driver's actual Strategy from the race Stints, scores Strategy Match (top-1 and top-3) and Stop Window hits independently, flags the race as a Neutralised Race if any `NeutralisationPeriod` is present, marks retired or never-stopped drivers unscoreable, and returns a race-level summary of top-1, top-3 and Stop Window hit counts over scoreable drivers.

**Shape of the result.** `RaceComparison` carries three things: a `scores` dict keyed by driver, a `neutralised_race` flag, and a `RaceSummary` with `scoreable_drivers`, `top_1_matches`, `top_3_matches`, and `stop_window_hits`. Each `DriverScore` carries the driver's `ActualStrategy` (or `None` when unscoreable), the two Strategy Match booleans, a `stop_window_hits` tuple with one entry per actual stop, and an `unscoreable` flag. `ActualStrategy` keeps the Compound sequence and the raw `stop_laps` (end lap of each non-final Stint).

**Decisions.**

- *Where the second call reads from.* The call takes a whole `RaceWeekend`, not just `predictions + RaceOutcome`. The ticket 01 comment points out that "retired" can only be inferred from `last_stint.end_lap < race_laps`, and `race_laps` lives on `PreRaceInfo`. Passing the weekend keeps the public surface narrow (one object) and matches `predict`'s shape.
- *Which windows to compare against.* The ticket 05 comment says "the n-th actual stop against the n-th predicted Stop Window", and that an actual Strategy absent from the prediction counts as no Strategy Match. I look up the Candidate Strategy whose compound sequence equals the actual one and score the n-th stop against the n-th window of that candidate. When the actual Strategy is absent from the prediction, each stop records a `False` hit so the per-stop tuple length still equals the number of actual stops; the summary's `stop_window_hits` counts only `True` entries and so is unaffected.
- *Retirement vs lapped finish.* With the current `RaceOutcome` shape there is no finishing status, so retirement is inferred from the last Stint ending before `race_laps`. This folds lapped finishers into "retired" and marks them unscoreable; the loader in ticket 07 should carry a finishing status to split the two (noted as a follow-up in that ticket's inherited comments).
- *What makes a driver unscoreable.* Three conditions: no Stints at all, a single Stint (never pitted — a Dry Race requires two Compounds so this is also a non-finish), or the last Stint ending before the race distance. All three produce the same `unscoreable=True, actual=None, stop_window_hits=()` shape.
- *Mirrored Strategy ties.* Strategy ordering within a mirrored tie (ticket 09) is left as whatever `predict` produces. Tests avoid depending on it by driving the actual Stints from `prediction.candidates[0].strategy` rather than hard-coding a Compound sequence.

**Testing.** `tests/test_compare_with_actual_race.py` goes through the public calls only: build a weekend with the hand-built helpers, call `predict`, build actual Stints by hand, call `compare`, and assert on the result. Thirteen scenarios cover actual-Strategy extraction, top-1 / top-3 matching, "outside the window still matches on Compounds", per-stop window hits, the n-th-stop-vs-n-th-window rule, Safety Car and VSC flags, retired and never-stopped drivers, and the race summary over scoreable drivers.

**Deviations.** None from the ticket. The spec's section "A second call takes those predictions plus the race's actual Stints and returns the comparison" is literally honoured; the implementation also reads `race_laps` from the weekend (needed for retirement) which the spec implicitly allows.

**Follow-ups and known limitations.**

- Lapped finishers are currently treated as retired. Ticket 07 (FastF1 loader) is the natural place to populate a `finishing_status` on `RaceOutcome`.
- Mirrored Strategy ties can push a driver's actual Strategy from top-1 to top-2 purely on iteration order; ticket 09 is the owner.
- The scorer deliberately does not expose a reason string for unscoreability. If a backtest or UI needs to split "retired" from "never pitted", a `reason` enum can be added without changing the summary counts.
