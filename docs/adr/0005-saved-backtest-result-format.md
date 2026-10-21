# Saved Backtest Result format

A full Backtest run writes two files side by side in a `results/backtest/` folder: a machine-readable **JSON** data file (`<date>_<label>.json`) and a plain-text **Markdown** summary (`<date>_<label>.md`) generated from it. Both are committed to the repo, so GitHub renders the summary without anything checked out and the data file powers the compare command (ticket 06) and any later tuning.

## Format

- **JSON**, UTF-8, two-space indent. Python stdlib covers read and write; a human can diff it on a PR; the compare command can load two of them without extra dependencies. The file carries `"format_version": 1` at the top so a reader can refuse or migrate an older file instead of mis-parsing it.
- Only **per-race records**, **Excluded Races** and **run metadata** are stored. Every aggregate on `BacktestResult` (headlines, race-averaged, breakdowns, Degradation source counts) is derivable from the per-race records plus `Settings`, so a reload recomputes them with the same code path `run_backtest` used. A later aggregation change then benefits an old file without migrating it.
- Enum members serialise as their `.value` string (`DegradationSource.LONG_RUNS` → `"long_runs"`, `ExclusionReason.NOT_DRY_RACE` → `"not a Dry Race"`); JSON has no enum type and the string form is already the printed form. The sprint/conventional breakdown bool key isn't serialised at all — it's recomputed from `RaceResult.is_sprint_weekend` on load, matching the formatter's `True`/`False` → `sprint`/`conventional` rendering. `by_circuit` ordering follows per-race insertion order in the saved file; Python dict equality is order-independent and the formatter sorts at print time, so order in the file doesn't matter for identity.

## What's saved per race

Everything on `RaceResult`: `season`, `event`, `circuit`, `is_sprint_weekend`, `neutralised_race`, `estimated_pit_loss`, `actual_stops`, the `RaceSummary` (`scoreable_drivers`, `top_1_credit`, `top_3_credit`, `stop_window_hits`) and the per-race `degradation_sources` map. **Scores and metadata only, never raw timing data** — a saved file for a four-season Backtest is a few tens of KB, safe to commit.

## What's saved as run metadata

Label, run date and time (ISO 8601 UTC), code commit, uncommitted-changes flag, seasons in scope, and every field of `Settings` (which includes `tuning_seasons` and `held_out_season`). The commit and the uncommitted-changes flag trace a result back to the code that made it; the seasons in scope let the compare command warn when two results cover different races; `Settings` goes in whole so a tuned run reads back with the same partition and the same thresholds.

## What's NOT saved

- Weekend data (laps, Stints, Sessions, outcomes). The Backtest Result is a score file, not a dataset.
- Aggregates on `BacktestResult` (headlines, breakdowns, source counts). Derivable, so re-computed on load.
- Progress output. Printed at run time only.

## Smoke Set runs

Smoke Set runs print their result but don't save by default (spec story 43). Saving is opt-in through the CLI's `--label` flag; without a label the Backtest prints only. A full-era baseline run (ticket 09) will be the first saved Backtest Result.

## Considered alternatives

- **Pickle**: rejected — opaque to a reader, tied to Python version and class paths, and the compare command would need the exact `BacktestResult` import graph to load one. JSON is readable on GitHub.
- **YAML**: rejected — extra dependency and no clear win over JSON for data that is mostly numbers.
- **Also persist aggregates in the file**: rejected — they're derivable, so persisting them opens up drift between the stored aggregates and the per-race records. Keeping only the per-race records makes the file the source of truth.
- **One file (data embedded in markdown)**: rejected — mixes a human target and a machine target, and the compare command would have to parse markdown to reach the numbers.

## Versioning

`format_version: 1` is the only version today. A breaking change (new required field, renamed field, different enum encoding) bumps the version; the loader refuses an unknown version rather than guessing. Additive, defaulted fields (a new optional per-race flag, say) stay at version 1 — old files load with the default, new files save the value. Removed fields also stay at version 1 — the loader ignores unknown keys.
