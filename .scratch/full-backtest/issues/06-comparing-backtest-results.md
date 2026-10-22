# 06: Comparing two Backtest Results

**What to build:** A public call and a command compare mode take two saved Backtest Results and show the before, after and change for every headline score and breakdown; the races whose credit moved most in each direction; and warnings when the in-scope races, Excluded Races or Held-out Season differ between them. See `../spec.md`.

**Blocked by:** 05 (Saving Backtest Results)

**Status:** done

- [x] Comparing two hand-built results reports every headline and breakdown change correctly
- [x] The biggest-moving races in each direction are listed
- [x] Different scope, Excluded Races or Held-out Season produce a clear warning
- [x] The command's compare mode prints the comparison for two saved results
- [x] Tests go through the public compare call

## Implementation notes

**What was built (2026-10-22).**

- `src/f1_strategy/backtest_compare.py`: a new module holding the two
  public calls `compare_backtest_results(before, after, *, before_metadata=None, after_metadata=None, top_n=5) -> BacktestComparison`
  and `format_comparison(comparison) -> str`, plus the result dataclasses
  (`ScoreChange`, `AveragedChange`, `ScoreBucketDiff`, `AveragedBucketDiff`,
  `RaceMovement`, `BacktestComparison`).
- `BacktestComparison` carries, derivable from the two `BacktestResult`s:
  pooled score diffs for the five headline buckets (green, Neutralised,
  all, Tuning Seasons, Held-out Season); race-averaged diffs for the
  three headline buckets (green, Neutralised, all); breakdown diffs by
  season / circuit / sprint; the top-N biggest-moving races in each
  direction (by per-race top-1 Strategy-Match rate); and a tuple of
  warnings for scope differences.
- `ScoreChange` carries `before_numerator`, `before_denominator`,
  `after_numerator`, `after_denominator`, `before_pct`, `after_pct` and
  `change_pp` (the delta in percentage points). `change_pp` is `None`
  when either side had a zero denominator; the formatter prints
  `no change computable` for that case rather than making up a delta.
  Same shape for `AveragedChange`, with `before_mean`/`after_mean`
  (0–1 means from `rate_sum / races_with_scoreable`).
- `RaceMovement` carries each race's `before_rate` and `after_rate`
  (top-1 credit per scoreable driver) and `change_pp`. Only races scored
  on both sides with scoreable drivers on both sides contribute; a race
  with `change_pp == 0` is skipped so the gainers/losers lists hold
  only races whose credit actually moved.
- Warnings cover the four scope dimensions:
  - `metadata.seasons_in_scope` differ (only emitted when both sides
    pass metadata; the compare call still works without metadata, for
    tests and library callers that already hold the results)
  - the per-run `tuning_seasons` or `held_out_season` partition differs
    (these are on `BacktestResult` itself, so always available)
  - the set of `(season, event)` scored races differs
  - the set of `(season, event, reason)` Excluded Races differs
  - the set of races with `estimated_pit_loss=True` differs **among
    races scored on both sides** — this is the extra warning the user
    asked for, since comparing a measured Pit Loss on one side with an
    estimated Pit Loss on the other isn't apples-to-apples. The
    `scored races differ` warning already covers races that only appear
    on one side, so flagging them again here would be noise.
- `format_comparison` prints: warnings first (so they're not missed at
  the end of a long run), then pooled headlines (five buckets), race-
  averaged headlines, by-season, by-circuit, sprint vs conventional
  breakdowns, biggest gainers, biggest losers. Breakdown keys present
  on only one side get an empty `ScoreTotals` on the missing side; the
  formatted percentage reads `—` and the delta reads `no change computable`.
- `src/f1_strategy/cli.py`: new `compare` subcommand that takes two
  file paths, loads both with `load_backtest_result`, calls
  `compare_backtest_results` (with metadata for both), and prints a
  header naming the two run labels plus `format_comparison`. Returns
  exit 0.
- `src/f1_strategy/__init__.py`: re-exports `BacktestComparison`,
  `ScoreChange`, `AveragedChange`, `ScoreBucketDiff`, `AveragedBucketDiff`,
  `RaceMovement`, `compare_backtest_results` and `format_comparison`.

**Decisions and alternatives rejected.**

- *Per-race movement metric: top-1 Strategy-Match rate.* The spec story
  41 asks for "the races that moved most"; the natural per-race number
  is the one the race-averaged headline sums. Top-1 credit / scoreable
  drivers is 0–1 per race, aligns with the mean-of-rates view, and lets
  the gainers/losers list show the same percentage that the headline
  does. Rejected: a composite "credit moved on top-1 + top-3 + stop
  window" score, which would hide which of those three a race moved
  on, and would need weights.
- *Top-N default of 5.* Enough to cover the biggest shifts after a
  change without flooding the output. The `top_n` argument lets the
  compare command (or a notebook) ask for a longer list.
- *Scope warnings include an "estimated Pit Loss flipped" warning.*
  The user explicitly asked for this at the top of the ticket. The
  spec's story 42 doesn't name it, but ticket 05's review feedback
  flagged `estimated_pit_loss` as the per-race Pit Loss provenance
  field; two runs where one race flipped from measured to estimated
  (e.g. the loader learned a pit-lane entry for a previously-estimated
  circuit) are not comparing like-for-like for that race's score, so
  the compare says so. Narrowed to races scored on both sides, so a
  race added or removed from scope only emits the broader "scored
  races differ" warning.
- *Scope warnings about `tuning_seasons` / `held_out_season` read from
  `BacktestResult`, not from `metadata.settings`.* Both carry the
  partition; `BacktestResult` is enough for a library caller that
  constructed results by hand without saving them, and metadata-only
  callers still have the information via `settings`. If the two ever
  disagree (e.g. a hand-edited file), the result's copy is what the
  run actually used, so that's the one to warn against.
- *Breakdown handling for keys on only one side.* Reported with an
  empty `ScoreTotals` on the missing side (zero denominator → None
  percentage → no delta). Alternative: raise or drop the key. Rejected
  — the compare's whole purpose is to surface what moved, and a season
  / circuit that appeared on one side but not the other is a scope
  change worth seeing in the output next to the breakdown it belongs
  in. The "scored races differ" warning already summarises the race-
  level view at the top; the breakdown's `—` makes which group's shape
  changed visible.
- *CLI subcommand name: `compare`.* Matches the spec's "compare mode"
  wording. Takes two positional path arguments (before, after); no
  flags. The command's existing `backtest` subcommand sits next to it
  in `main` so the single-race mode (`uv run f1-strategy 2024 "Italian
  Grand Prix"`) is unchanged.
- *`compare_backtest_results` takes `BacktestResult`s, not file paths.*
  Keeps the public API testable without touching the filesystem (the
  tests already round-trip through `save_backtest_result` /
  `load_backtest_result`); the CLI does the I/O.
- *`AveragedBucketDiff` only for green/Neutralised/all, not for the
  breakdowns.* The spec and `BacktestResult` only carry race-averaged
  figures for those three; the breakdowns are pooled-only (ticket 04's
  own limitation, recorded in that ticket's follow-ups). A race-
  averaged by-season / by-circuit view would be a new feature on
  `BacktestResult`, not on the compare.
- *Delta unit: percentage points.* "pp" matches how the headline is
  reported ("Top-1 Strategy Match: 7.5/18 (42%)"); a reader can see
  the change in the same units as the before/after figures.

**Deviations from the ticket / spec.**

- The spec's story 42 names "in-scope races, Excluded Races or
  Held-out Season" as the warning triggers; I also warn when
  `tuning_seasons` differs (so a run that moved a season from Tuning
  to Held-out is as visible as one that changed the Held-out Season),
  and when the set of races with an estimated Pit Loss differs (per
  the user's request at the top of this ticket). Neither narrows what
  the spec asks for.

**Testing.**

- `tests/test_backtest_compare.py` (13 tests, all through the public
  `compare_backtest_results` call with hand-built weekends, round-
  tripped through `save_backtest_result` and `load_backtest_result`):
  - pooled and race-averaged green-race headlines report before, after
    and change (direction, not exact figures, so the test survives any
    future split-tie-credit tweak that moves the baseline rate)
  - breakdowns show per-group change (`by_season`, `by_circuit`) with
    directions aligned to which races moved
  - a breakdown key on only one side has an empty bucket on the other
    side (zero denominator, `before_pct=None`)
  - biggest-moving races in each direction are listed, with their
    before/after rates and `change_pp`
  - warnings for: seasons-in-scope differ, scored races differ,
    excluded races differ, `held_out_season` differs, `tuning_seasons`
    differ, estimated-Pit-Loss flipped on a race scored both sides
  - identical results produce no warnings
  - `format_comparison` output contains headline, breakdown, biggest-
    movers and WARNINGS sections
  - the CLI `compare` mode loads two files and prints the comparison
- Full fast suite: 148 passed (was 135 before this ticket; 13 new).
  No slow tests re-run as part of this ticket — the compare path
  doesn't touch the FastF1 loader.

**Open questions, known limitations and follow-ups.**

- `AveragedBucketDiff` is only provided for the three top-level race-
  averaged figures (green / Neutralised / all races) because that's
  what `BacktestResult` carries. If a future ticket adds race-averaged
  by-season or by-circuit, the compare only needs to add those keys
  to the `BacktestComparison` dataclass; the diff shape is already
  shared via `_averaged_change`.
- The "biggest movers" list uses only top-1 rate. If a reader wants
  to see races where only Stop Window moved, they can read the per-
  race `RaceResult` directly. A `top_losers_by_stop_window` list is a
  small addition if needed; left as a follow-up.
- The compare command returns exit 0 even when warnings fire. The CLI
  prints them prominently (at the top of the output), but a tuned-run
  CI pipeline that wanted to fail on scope drift would need a
  `--strict` flag or similar. Not asked for by the spec; left as a
  follow-up.
- `format_comparison`'s output is plain text wrapped at natural line
  lengths. If a later ticket wants a markdown table (so GitHub renders
  it), the same split as `format_backtest`'s `markdown=True` follow-up
  would apply.
- When metadata is omitted on either side, the compare still works
  but can't emit the `seasons_in_scope` warning. The CLI always
  provides metadata (both sides come from `load_backtest_result`), so
  this only matters to library callers.

**Review feedback to the user.**

- Ticket 09 (first full baseline Backtest Result) will produce the
  first file this compare command can read in anger. A future tuned
  run from the tuning spec will produce the "after" file; the compare
  then shows which races the tuning helped and which it hurt, with
  the Tuning Seasons vs Held-out Season split visible in the pooled
  diff.
- If ticket 16 (location-name aliases) lands between a baseline and a
  tuned run, the "estimated Pit Loss differs" warning will fire for
  Monaco 2022, Marina Bay 2022 and Miami Gardens 2025 — the Pit Loss
  for those races will have flipped from estimated to measured. That
  warning is correct behaviour: it signals the compare isn't apples-
  to-apples on those races' Pit Loss, so if their score moved, part
  of the move is the loader change rather than the tuning.
- No new domain terms were introduced; the terms the compare uses
  (Backtest Result, Excluded Race, Held-out Season, Tuning Seasons,
  Pit Loss, Strategy Match) are already in `CONTEXT.md`.
- The compare carries no decisions that look hard to reverse or
  surprising without context, so no new ADR is proposed. The file
  format and versioning rules are already in ADR-0005.
