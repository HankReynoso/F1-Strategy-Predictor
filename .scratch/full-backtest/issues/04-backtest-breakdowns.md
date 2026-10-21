# 04: Backtest breakdowns

**What to build:** The Backtest Result gains race-averaged versions of the headline scores; breakdowns by season, by circuit, by sprint vs conventional, and Tuning Seasons (2022–2024) vs Held-out Season (2025); counts of each Degradation source used; and the Excluded Race count. Tuning Seasons and Held-out Season are settings of the run, not hard-coded into scoring. Every figure shows its numerator and denominator, and breakdowns are derivable from the per-race records. The command prints them. See `../spec.md`.

**Blocked by:** 02 (Tracer bullet)

**Status:** done

- [x] Race-averaged scores are reported next to the pooled ones, and differ as expected when races have different numbers of scoreable drivers
- [x] Season, circuit and sprint/conventional breakdowns add up to the totals
- [x] Tuning Seasons and Held-out Season are reported side by side, and come from the run's settings
- [x] Degradation source counts and the Excluded Race count are reported
- [x] Tests go through the Backtest call with hand-built weekends

## Implementation notes

**What was built (2026-10-21).**

- `src/f1_strategy/settings.py`: `Settings` gains two fields,
  `tuning_seasons: tuple[int, ...] = (2022, 2023, 2024)` and
  `held_out_season: int | None = 2025`. The Backtest reads them to
  partition scored races into Tuning Seasons vs Held-out Season; nothing
  in `predict()` or `compare()` touches them, so the model is unchanged.
- `src/f1_strategy/backtest.py`: `BacktestResult` extended with
  everything ticket 04 names, all derivable from the per-race `races`
  tuple:
  - `green_headline_averaged`, `neutralised_averaged`,
    `all_races_averaged` — a new `RaceAveraged` dataclass. For each race
    with scoreable drivers it sums `top_1_credit/scoreable_drivers`
    (same for top-3), and for each race with actual stops it sums
    `stop_window_hits/actual_stops`. The per-race denominators are
    carried as `races_with_scoreable` and `races_with_stops`, so the
    numerator/denominator rule holds (the printed percentage is
    `rate_sum / races_with_scoreable`). Races with no scoreable drivers
    don't contribute to the Strategy-Match averages, which keeps a tiny
    race from dividing by zero or dragging the mean to zero.
  - `by_season: Mapping[int, ScoreTotals]`,
    `by_circuit: Mapping[str, ScoreTotals]`,
    `by_sprint_weekend: Mapping[bool, ScoreTotals]`. Pooled across each
    group's races, so they add up to `all_races` by construction.
  - `tuning: ScoreTotals`, `held_out: ScoreTotals` — pooled across races
    whose season is in `settings.tuning_seasons` and
    `settings.held_out_season` respectively.
  - `tuning_seasons: tuple[int, ...]`, `held_out_season: int | None` —
    copies of the run's settings, carried on the result so a saved
    Backtest Result can show which seasons it treated as which.
  - `degradation_source_counts: Mapping[DegradationSource, int]` —
    summed across races, where each `RaceResult` now carries its own
    `degradation_sources` map.
- `RaceResult.degradation_sources` is built from the predictions
  returned by `predict()`: for each unique team in the race (deduped
  because a team's two drivers share the same `team_degradation` dict),
  it counts the per-Compound estimates by `DegradationSource`. So a
  three-team race with three dry Compounds contributes 9 total counts,
  distributed across the sources the predictor resolved for each
  (team, Compound) pair.
- `format_backtest` now prints: pooled green headline → race-averaged
  green headline → Neutralised-only → all-races → by season → by
  circuit → sprint vs conventional → Tuning Seasons (listed in the
  heading) → Held-out Season (listed in the heading) → Degradation
  source counts → Excluded Races. Every pooled score keeps the
  numerator/denominator/percentage format from ticket 02; the
  race-averaged lines use "mean X% over N race(s)" with N shown
  explicitly so a small race-set is obvious.
- `src/f1_strategy/__init__.py` re-exports the new `RaceAveraged`
  dataclass.

**Decisions and alternatives rejected.**

- *Race-averaged shape as `RaceAveraged`, not a wider `ScoreTotals`.*
  The pooled totals share one shape (`ScoreTotals`) across every
  grouping. The race-averaged figure is of a different shape — it has
  per-race rates summed, not per-driver credit — so a separate
  dataclass keeps both readable. Alternative: shoehorn race-averaged
  values into `ScoreTotals` by also storing per-race rate sums.
  Rejected because it would make the breakdowns' `ScoreTotals` carry
  fields that only make sense for the headline.
- *Race-averaged denominators.* The denominator is the number of races
  that could contribute, which differs for Strategy Match (races with
  at least one scoreable driver) and for Stop Window (races with at
  least one actual stop). Carrying both means the numerator/denominator
  rule holds without special-casing in the formatter. A single
  "contributing races" count would misreport a race where everyone
  retired after one lap or finished with no stops.
- *Degradation source counting by team × Compound.* Teams, not drivers,
  because the predictor's `team_degradation` is a per-team structure
  and two drivers on one team would otherwise be double-counted. The
  per-race record keeps the finer-grained per-(team, Compound) count
  so a future ticket could break the counts down by Compound; the
  Backtest Result's run-level `degradation_source_counts` sums across
  Compounds for the printed figure. Alternative: count per team only
  (one entry per team, picking any one Compound's source). Rejected
  because a team can have different sources for different Compounds
  (Long Runs on Medium, field-average fallback on Hard), and losing
  that detail would hide how often fallbacks were used.
- *Tuning / Held-out as settings, not constants.* `Settings` carries
  the partition. The spec is explicit that these are "settings of the
  run, not hard-coded into scoring" so the tuning spec can reuse them.
  The defaults match the spec's choice (2022-2024 Tuning, 2025
  Held-out), and the breakdowns test exercises a non-default partition
  to pin down that behaviour. Alternative: a module-level constant.
  Rejected on the spec's say-so.
- *`held_out_season` as `int | None`.* Allows a future run where
  everything is Tuning (no held-out season) without a special sentinel;
  the formatter prints "Held-out Season" without a year when it is
  `None`. The current default is `2025` to match the spec.
- *Breakdown bucket type for sprint vs conventional.* `dict[bool,
  ScoreTotals]`, not an enum. Rejected an enum because `is_sprint_weekend`
  is already a bool on `PreRaceInfo` and `RaceResult`, and a bool key
  reads naturally in tests (`by_sprint_weekend[True]`). The formatter
  renders `True`/`False` as `sprint`/`conventional` for people.
- *Where to compute aggregates.* In `run_backtest`, same place the
  pooled headlines are already built. The spec notes that aggregates
  should be derivable from the per-race records, so a comparison
  (ticket 06) can recompute them. Alternative: expose only
  `races`/`excluded` and let the formatter and saver each recompute.
  Rejected: ticket 05 (saving) will want a canonical set of numbers to
  write, and recomputing in the formatter would make the formatter
  know about group keys that the saver would then have to also know.
- *Formatter growth.* Kept inside `format_backtest`. The output is
  longer now (headline + averaged + Neutralised + all + three
  breakdowns + tuning/held-out + sources + exclusions), but each
  section is one block with a heading, so a reader can skim.
  Alternative: separate `format_breakdowns(result)` call. Rejected
  because the command only ever prints the whole thing; splitting
  wins nothing.

**Deviations from the ticket / spec.**

- None known. The ticket's four acceptance criteria map 1:1 to the
  tests in `tests/test_backtest_breakdowns.py`; the spec's broader
  aggregate list (user stories 18-25, 32, 13) is all present on
  `BacktestResult`.

**Testing.**

- `tests/test_backtest_breakdowns.py` (10 tests, all through
  `run_backtest` with hand-built weekends and a fake loader):
  - race-averaged scores sit next to the pooled headline and differ
    from them when race sizes differ (0.5/1 top-1 credit on one race +
    0/2 on another: pooled ≈ 16.7%, averaged = 25%)
  - race-averaged equals pooled when races have the same scoreable
    count
  - season, circuit and sprint-vs-conventional breakdowns add up to
    `all_races` (scoreable drivers, top-1 credit, actual stops, races
    all reconciled)
  - Tuning and Held-out partitions follow the default `Settings`
  - Tuning and Held-out partitions follow a non-default `Settings`
    (`tuning_seasons=(2022, 2023, 2025), held_out_season=2024`), proving
    they are not hard-coded
  - per-race Degradation source counts are populated and sum into the
    run-level `degradation_source_counts`
  - the Excluded Race count is in the formatted output when loader and
    predictor both have failures
  - the formatter prints every new section (race-averaged, by season,
    by circuit, sprint vs conventional, Tuning Seasons heading with
    seasons listed, Held-out Season heading with year listed,
    Degradation source counts)
- Full fast suite: 111 passed (was 98 before ticket 02 landed; 11 new
  tests plus ticket 02's +12 land us here). No slow tests re-run as
  part of this ticket because the breakdowns don't touch the FastF1
  loader; the existing `tests/test_backtest_real_data.py` still runs
  under `-m slow` and already covers the loader path.

**Open questions, known limitations and follow-ups.**

- The breakdowns are keyed on `season`, `circuit`, `is_sprint_weekend`.
  A future ticket (saving, ticket 05) will likely want to serialise
  `by_circuit` with a stable ordering (sorted by circuit name is the
  obvious choice, matching the formatter). The current
  `Mapping[str, ScoreTotals]` doesn't commit to that; the formatter
  sorts at print time.
- `RaceAveraged` keeps the numerator/denominator rule but the rate_sum
  it carries is less meaningful on its own than per-race credit. The
  formatter divides and shows "mean X% over N race(s)". If a comparison
  (ticket 06) wants to show the race-averaged change between two runs,
  it should compute `rate_sum / races_with_scoreable` and compare that.
- `held_out.races + tuning.races` won't equal `all_races.races` once
  there are scored races outside both windows (e.g. a 2026 race in a
  2022-2025 Tuning + 2025 Held-out partition). That matches the spec
  ("2026 races join once there is enough same-era history") and the
  test only asserts the equality for the 2022-2025 scope. If a future
  run spans eras, the formatter will show the two aggregates and the
  reader can see from the race list what else is in `all_races`.
- `by_season`, `by_circuit`, `by_sprint_weekend` do not yet have
  race-averaged counterparts. If a future user story wants
  "race-averaged by season", it's a 10-line addition over the same
  grouping; no shape change required.

**Review feedback to the user.**

- Ticket 05 (saving) will serialise `BacktestResult`, including the new
  `Mapping` fields and the `DegradationSource` enum keys. JSON doesn't
  carry enum members or `bool` keys natively, so a serialiser will need
  to encode them as strings; the enum's `.value` and
  `"sprint"/"conventional"` are the natural choices and match the
  formatter.
- Ticket 06 (comparing) can diff every ScoreTotals and RaceAveraged
  field pairwise. The only field pair that doesn't diff cleanly is
  `tuning_seasons` / `held_out_season`: a run with a different
  partition isn't comparing like-for-like and the comparison should
  warn (spec story 42).
- Ticket 03 (Pit Loss before the era) runs in parallel with this one;
  both touch different files (ticket 03 lives in `fastf1_loader.py`
  and `report.py`), so a rebase should be mechanical.
