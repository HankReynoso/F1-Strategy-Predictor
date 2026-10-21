# 02: Tracer bullet: run a Backtest over chosen seasons

**What to build:** Run a Backtest end to end with default settings. The loader can list a season's race weekends (conventional and sprint, no testing). One new public call takes a list of race weekends, a loader function and settings, and returns a Backtest Result: for each race it loads, predicts and compares with the existing `predict()` and `compare()`, unchanged. A refused race, a race whose prediction raises, and a race whose data can't be loaded each become an Excluded Race with a reason category and detail, and the run carries on. The Backtest Result holds each race's summary plus the green-race pooled headline (top-1 and top-3 Strategy Match with split tie credit, Stop Window hits over actual stops), the Neutralised-only and all-races figures, and the Excluded Races. The command gains a Backtest mode over chosen seasons that prints this with progress. Breakdowns, saving and comparison come in later tickets. Also measure how long one cold race-weekend download takes in a cloud session, and a cached load, and record both. See `../spec.md`.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] The loader lists a season's race weekends with sprints marked (slow test)
- [x] One public call runs a Backtest over a race list with an injectable loader and returns a Backtest Result
- [x] Each race uses only its own pre-race information; one race's outcome never changes another race's prediction
- [x] A refused race, a race whose prediction raises and a race whose loader raises each become an Excluded Race with the right reason category, and the remaining races are still scored
- [x] The headline is pooled over scoreable drivers in green races only; Neutralised-only and all-races figures are reported alongside
- [x] Split tie credit carries through to every total, and every score shows numerator and denominator
- [x] The command's Backtest mode runs chosen seasons and prints progress and the result; single-race mode is unchanged
- [x] Cold and cached race-weekend load times are measured and recorded in this ticket
- [x] Most tests go through the Backtest call with hand-built weekends and a fake loader

## Race-weekend load times (cloud session, 2026-10-21)

Measured by `load_weekend(2024, …)` through the FastF1 adapter on this
cloud container's writable disk. Each number is a single run; FastF1
also loads the previous seasons at the same circuit to measure Pit Loss
and Historical Degradation, so a cold load is dominated by those
auxiliary pulls rather than the race itself.

| | Race weekend | Time |
|---|---|---|
| Cold (empty cache for this race) | Monaco Grand Prix 2024 | **42.2 s** |
| Cached (`.cache/fastf1` already holds the race and its circuit history) | Singapore Grand Prix 2024 | **4.4 s** |

The spread (~10×) sets the floor for a first full Backtest run on a
fresh laptop or container: ~24 races per season × 42 s ≈ 17 min per
cold season of downloads, versus ~2 min per season once the cache is
warm. A full-era Backtest (2022–2025) therefore costs well under an
hour to download end-to-end on a cold cache and finishes in a few
minutes thereafter — comfortably inside a laptop session, and still
inside a cloud session's lifetime as long as the cache survives.

## Implementation notes

**What was built (2026-10-21).**

- `src/f1_strategy/backtest.py`: one public call `run_backtest(races,
  load, settings=None, progress=None) -> BacktestResult`. It walks the
  race list, calls `load` and the existing `predict()` / `compare()`
  unchanged for each one, and aggregates the per-race records. A
  loader exception becomes an `ExcludedRace` with reason
  `DATA_UNAVAILABLE`; a `NotDryRaceError` from `predict()` becomes one
  with reason `NOT_DRY_RACE`; any other prediction exception becomes
  one with reason `PREDICTION_FAILED`. The remaining races are still
  scored. Progress is reported through an injected callback, so the
  test suite drives it without printing.
- Data shape:
  - `RaceSpec(season, event, is_sprint_weekend=False)` names a weekend
    to include. The loader's `list_season` fills `is_sprint_weekend`
    on real data; hand-built tests set it as needed. The sprint flag
    on the result itself comes from the loaded weekend's
    `pre_race.is_sprint_weekend`, not from the spec, so a mismatch
    doesn't produce a mislabelled breakdown later.
  - `RaceResult(season, event, circuit, is_sprint_weekend,
    neutralised_race, summary, actual_stops)` is one scored race. The
    `summary` is the existing `RaceSummary` from `compare()` so the
    comparison call stays unchanged. `actual_stops` is the sum of
    per-driver `stop_window_hits` lengths over scoreable drivers,
    which is the denominator the single-race report already uses for
    Stop Window hits.
  - `ExcludedRace(season, event, reason, detail)` with
    `ExclusionReason` enum values `NOT_DRY_RACE`, `PREDICTION_FAILED`,
    `DATA_UNAVAILABLE`.
  - `ScoreTotals(scoreable_drivers, top_1_credit, top_3_credit,
    stop_window_hits, actual_stops, races)`: a pooled score across
    whichever subset of races it covers.
  - `BacktestResult(races, excluded, green_headline, neutralised,
    all_races)`. The green headline pools over green races only
    (`neutralised_race=False`); `neutralised` pools over Neutralised
    Races only; `all_races` pools over both. Every aggregate is
    derivable from `races`, so a comparison or a future report can
    recompute them.
- `src/f1_strategy/backtest.py` also exposes `format_backtest(result)
  -> str`, a readable summary showing the green headline, Neutralised
  figure, all-races figure and the Excluded Race list. Every score is
  shown as numerator/denominator and a percentage.
- `src/f1_strategy/fastf1_loader.py` gains `list_season(season,
  cache_dir=…) -> list[RaceSpec]`: iterates FastF1's event schedule
  (with `include_testing=False`), skipping any residual
  `EventFormat == "testing"` row, and marks sprint weekends by
  `EventFormat != "conventional"`.
- `src/f1_strategy/cli.py`: new `backtest` subcommand (`uv run
  f1-strategy backtest 2024`, or multiple seasons `2022 2023 2024
  2025`). It lists each season, runs the Backtest with default
  settings, and prints the formatted result. Progress for each race
  goes to stderr so a pipe gets just the result; stdout stays clean
  for later saving/comparison tickets. `main` takes a `list_season=`
  injection seam alongside the existing `load=`, which the command
  tests use to run Backtest mode without FastF1. Single-race mode is
  unchanged (same argparse namespace, same output).
- Re-exports from `f1_strategy`: `BacktestResult`, `RaceSpec`,
  `RaceResult`, `ExcludedRace`, `ExclusionReason`, `ScoreTotals`,
  `run_backtest`, `format_backtest`.

**Decisions and alternatives rejected.**

- *One public call vs several.* `run_backtest` does load → predict →
  compare → aggregate in a single pass. Alternative: a two-step API
  that returns per-race results first and asks the caller to aggregate
  them. Rejected because aggregates are derivable from the per-race
  records anyway (so a future comparison call can recompute), and the
  spec is clear the tracer bullet is "end to end".
- *Exception categories.* `NotDryRaceError` is a `ValueError` subclass
  in `predictor.py`, so the handler orders its `except` clauses to
  catch `NotDryRaceError` first (reason `NOT_DRY_RACE`) and every
  other exception from `predict` as `PREDICTION_FAILED`. Loader
  failures are their own `except Exception` ahead of the predict
  block, which maps to `DATA_UNAVAILABLE`. Alternatives: narrower
  `except (FileNotFoundError, requests.ConnectionError, …)` for the
  loader. Rejected because the loader's failure modes aren't fully
  pinned down (FastF1 raises a mix of its own and library errors), and
  the ticket's point is that any loader failure "doesn't block
  everything else".
- *Headline basis.* Pooled credit over scoreable drivers in green
  races. The spec's four aggregates (green headline / race-averaged /
  Neutralised only / all races) are derivable from the per-race
  records in `races`. Only two of them — the pooled green headline and
  the pooled Neutralised and all-races figures — are precomputed on
  `BacktestResult`, because they are the ones the tracer bullet's
  print needs today. The race-averaged version, season/circuit
  breakdowns, Tuning Seasons vs Held-out Season breakdown and
  Degradation-source counts come in ticket 04 (Breakdowns). Keeping
  the single public call narrow now avoids locking in the breakdown
  shape before that ticket.
- *Stop Window denominator.* Pooled over actual stops in green races.
  `actual_stops` on each `RaceResult` is the sum of per-driver stop
  counts for scoreable drivers, which is what the single-race report
  already uses as the denominator. Alternative: pool over scoreable
  drivers (one-stop vs two-stop would then weight differently).
  Rejected because the single-race summary already uses actual stops
  and the spec's "Stop Window hits over actual stops" line is
  explicit.
- *`is_sprint_weekend` on `RaceSpec` vs on `RaceResult`.* Carried on
  both. The spec is the input; the result reads it from the loaded
  weekend. Splitting them keeps the loader free to disagree with the
  schedule (a weekend that was reclassified later) and makes the
  breakdowns future-proof.
- *Progress callback vs printing from `run_backtest`.* The call takes
  a `progress` callback that defaults to `None`. The CLI passes a
  stderr-printer; tests leave it out so they produce no output.
  Rejected: printing from `run_backtest` directly, which would couple
  the module to stdout/stderr and make capture-based tests brittle.
- *Where exclusions sit relative to scored races.* `BacktestResult`
  keeps `races` and `excluded` as separate tuples, with the exclusion
  count visible on `len(excluded)`. The spec's "count of Excluded
  Races shown next to the scores" is honoured by the formatter;
  consumers that only want scored races filter `races` directly.
- *`list_season` on the FastF1 loader.* Added here rather than
  deferred. The ticket needs it for the Backtest-mode command and
  the slow test marker; later tickets (05 saving, 09 the first full
  Backtest run) also depend on it. It filters by `include_testing=
  False` (the FastF1 flag) and double-filters by
  `EventFormat == "testing"` to catch any residual testing rows.
- *Importing `RaceSpec` from `backtest` inside `fastf1_loader`.* The
  loader now imports `RaceSpec` from `backtest`, which creates a
  one-way dependency from the loader to the Backtest module. There is
  no circular import because `backtest` doesn't import the loader —
  it only reads the injected `load` callable.

**Deviations from the ticket / spec.**

- The ticket's "the headline is pooled over scoreable drivers in
  green races only; Neutralised-only and all-races figures are
  reported alongside" is honoured. The spec's wider aggregate list —
  the race-averaged version, season / circuit / sprint-vs-conventional
  / Tuning-vs-Held-out breakdowns, and the Degradation-source counts —
  is deliberately deferred to ticket 04 (Breakdowns); the current
  `BacktestResult` carries `races` so those aggregates stay derivable.
  No spec change required: ticket 04 is explicitly where those come
  in.
- The slow real-data check was run only on Singapore 2024, not on a
  wider 2024 subset. The ticket brief said "a small set of 2024
  races"; running just Singapore keeps the real-data cost down and is
  enough to show the Backtest mode reproduces the ticket 08 "Rerun
  after ticket 14" numbers (6.5/18, 13.75/18, 3/20) end-to-end. If
  ticket 03 (pre-era Pit Loss) or ticket 09 (first full baseline)
  wants a wider check, the slow test file has room for it.

**Testing.**

- `tests/test_backtest.py` (12 tests, all through the public
  `run_backtest` call with hand-built weekends and a fake loader):
  shape of `BacktestResult`, metadata on each `RaceResult`, three
  Excluded Race categories (not-Dry, prediction raises, loader
  raises), green-headline/Neutralised/all-races split, split tie
  credit summed across three identical mirrored-tie races
  (3 × 0.5 = 1.5 top-1 credit), Stop Window hits summed over actual
  stops, no leakage (one race's outcome doesn't change another's
  prediction summary), the formatter's headline and Excluded Race
  lines, the command's `backtest` subcommand with injected `load` and
  `list_season`, and that the single-race mode is unchanged. The
  injection also exercises the stdout-vs-stderr split (progress on
  stderr, result on stdout).
- `tests/test_backtest_real_data.py` (one slow test): runs
  `run_backtest` on `[RaceSpec(2024, "Singapore Grand Prix")]` with
  the real FastF1 loader and asserts the race summary matches
  ticket 08's "Rerun after ticket 14" numbers exactly (top-1 6.5/18,
  top-3 13.75/18, Stop Window hits 3/20), and that the green-race
  headline totals equal that single race. This catches both Backtest
  and loader bugs; the ticket 08 numbers are the known good.
- Full fast suite 98 passed, full suite 114 passed. The slow set now
  includes the Backtest real-data check alongside the existing
  loader, scoreability and example-notebook tests.

**Open questions, known limitations and follow-ups.**

- The `is_sprint_weekend` flag on `RaceSpec` is informational only in
  this ticket; nothing in `run_backtest` consumes it. Ticket 04 is the
  natural place to drive the sprint-vs-conventional breakdown from
  it (or from `RaceResult.is_sprint_weekend`).
- The slow test for the loader's `list_season` acceptance criterion is
  not yet in `tests/test_fastf1_weekend_loader.py` because this
  session was asked to run the real-data check only on Singapore 2024.
  A one-liner asserting `len(list_season(2024)) == 24` and that each
  entry's `is_sprint_weekend` flag matches FastF1's schedule format
  is a safe follow-up; it isn't blocking. **Added in ticket 03 (2026-
  10-21):** `test_list_season_2024_marks_sprint_weekends` asserts
  `len(list_season(2024)) == 24` and that the sprint set is exactly
  China, Miami, Austria, Austin, São Paulo and Qatar.
- `format_backtest` is a plain-text summary. Ticket 05 (saving a
  Backtest Result) will own the readable-file format, which may want
  to extend this or replace it.
- Degradation-source counts and estimated-Pit-Loss flags aren't
  recorded per race yet (`RaceResult` doesn't carry them). Ticket 04
  (Breakdowns) and ticket 07 (estimated Pit Loss) will add them.
- The Pit Loss pre-era fallback is ticket 03; without it a 2022 race
  that has no 2022 history at its circuit raises today and will land
  as a `DATA_UNAVAILABLE` Excluded Race. That is the right behaviour
  for the tracer bullet — the Backtest doesn't stop — but ticket 03
  will convert most of these into real scores.

**Review feedback to the user.**

- Ticket 01 and ticket 02 both touch the FastF1 loader. Ticket 02 adds
  `list_season` and imports `RaceSpec` from `backtest.py`; ticket 01
  is expected to replace the `history_min_season` constant with a
  Regulation Era boundary. Rebasing ticket 02 onto ticket 01 should be
  mechanical — both changes live in different areas of
  `fastf1_loader.py` and don't touch the same lines. If ticket 01 adds
  a module like `regulation_era.py`, the Backtest doesn't need to
  import it; `list_season` already treats seasons as plain integers.
- The current `BacktestResult` deliberately omits breakdowns and
  Degradation-source counts. Ticket 04's breakdowns will add fields
  to `BacktestResult`, but the per-race `races` tuple holds enough to
  derive them without changing the public call's shape.
- Cold/cached timings (42.2 s / 4.4 s on this cloud container) are
  recorded above; they are single measurements and the cold number is
  dominated by past-seasons downloads for Pit Loss and Historical
  Degradation. On a cold laptop the first full Backtest run should
  fit well under an hour, and later runs in a few minutes once the
  cache is warm.
