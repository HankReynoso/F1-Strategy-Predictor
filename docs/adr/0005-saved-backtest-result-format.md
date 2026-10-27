# Saved Backtest Result format

A full Backtest run writes two files side by side in a `results/backtest/` folder: a machine-readable **JSON** data file (`<date>_<label>.json`) and a plain-text **Markdown** summary (`<date>_<label>.md`) generated from it. Both are committed to the repo, so GitHub renders the summary without anything checked out and the data file powers the compare command (ticket 06) and any later tuning.

## Format

- **JSON**, UTF-8, two-space indent. Python stdlib covers read and write; a human can diff it on a PR; the compare command can load two of them without extra dependencies. The file carries `"format_version"` at the top (currently `3`) so a reader can refuse or migrate an older file instead of mis-parsing it.
- Only **per-race records**, **Excluded Races** and **run metadata** are stored. Every aggregate on `BacktestResult` (headlines, race-averaged, breakdowns, Degradation source counts) is derivable from the per-race records plus `Settings`, so a reload recomputes them with the same code path `run_backtest` used. A later aggregation change then benefits an old file without migrating it.
- Enum members serialise as their `.value` string (`DegradationSource.LONG_RUNS` → `"long_runs"`, `ExclusionReason.NOT_DRY_RACE` → `"not a Dry Race"`); JSON has no enum type and the string form is already the printed form. The sprint/conventional breakdown bool key isn't serialised at all — it's recomputed from `RaceResult.is_sprint_weekend` on load, matching the formatter's `True`/`False` → `sprint`/`conventional` rendering. `by_circuit` ordering follows per-race insertion order in the saved file; Python dict equality is order-independent and the formatter sorts at print time, so order in the file doesn't matter for identity.

## What's saved per race

Everything on `RaceResult`: `season`, `event`, `circuit`, `is_sprint_weekend`, `neutralised_race`, `estimated_pit_loss`, `actual_stops`, `predicted_strategy_stops` and `stop_window_laps` (from version 3; ticket 58), the `RaceSummary` (`scoreable_drivers`, `top_1_credit`, `top_3_credit`, `stop_window_hits`), the per-race `degradation_sources` map, and the race's Data Quality Warnings as a list of strings under `data_quality_warnings` (from version 2; ticket 39). The JSON key is the name ticket 34 gives the in-code field (`RaceResult.history_warnings` today), so that rename doesn't touch the file; ticket 26's race-control warnings join the same list. **Scores and metadata only, never raw timing data** — a saved file for a four-season Backtest is a few tens of KB, safe to commit.

## What's saved as run metadata

Label, run date and time (ISO 8601 UTC), code commit, uncommitted-changes flag, seasons in scope, whether the run was offline (`offline`, from ticket 36: read saved data only, never contacted FastF1 or OpenF1), and every field of `Settings` (which includes `tuning_seasons` and `held_out_season`). The commit and the uncommitted-changes flag trace a result back to the code that made it; the seasons in scope let the compare command warn when two results cover different races; `Settings` goes in whole so a tuned run reads back with the same partition and the same thresholds.

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

A breaking change (new required field, renamed field, different enum encoding) bumps the version; the loader refuses an unknown version rather than guessing, and keeps reading every older version it knows. Additive, defaulted fields (a new optional per-race flag, say) don't bump the version — old files load with the default, new files save the value. Removed fields don't either — the loader ignores unknown keys.

A new field also bumps the version when its absence would read as a real value rather than as "not recorded". Then an old reader refuses the new file instead of silently dropping the field, and the version tells a new reader whether the field was ever written.

- **Version 1** (tickets 05–30): everything above except Data Quality Warnings.
- **Version 2** (ticket 39): adds the required per-race `data_quality_warnings` list. Before this, the warnings were printed in the summary but never written to the data file, so a reload lost them. A version-1 file loads with no warnings, because none were saved, not because its races had none: the committed `2026-10-26_first-openf1-run` lists them in its `.md` but not its `.json`. The loader exposes the file's version as `RunMetadata.format_version`, and the compare command says it can't compare warnings when either side is version 1, rather than naming every warned race on the other side.

Rejected for version 2: saving the warnings as an optional field at version 1. This ADR's rule as first written allowed it, but an empty list would then mean both "this race had none" and "this file predates saved warnings". An older build would also silently drop warnings from a newer file. Recovering version-1 warnings from the `.md` summary was rejected as well: the data file is the source of truth, and the compare command doesn't parse markdown.

- **Version 3** (ticket 58): adds the required per-race `predicted_strategy_stops` (actual stops on a Strategy that was one of the driver's Candidate Strategies, the Predicted-Strategy Stops) and `stop_window_laps` (the summed width of their Stop Windows). They give Stop Window hits over Predicted-Strategy Stops and the average Stop Window width. A missing count would read as "0 Predicted-Strategy Stops", a real value, so the rule above bumps the version. A file before version 3 loads with both as `None` ("not recorded"), every aggregate built from them is `None` too, the summary prints "not recorded", and the compare command warns once that it can't compare them. Neither can be recovered for an old file: they need the per-driver Candidate Strategies, which a Backtest Result never saves. Both committed results (`2026-10-26_first-openf1-run`, version 1, and `2026-10-27_baseline`, version 2) load this way.

Rejected for version 3: saving the two keys as optional at version 2, for the same two reasons as version 2's warnings.

- **`offline` run metadata** (ticket 36), still version 3: an additive, defaulted field. A file without it loads as `offline: false`, and that is a true value, not a guess: offline mode didn't exist before ticket 36, so every run saved before it was online. An older build reading a newer file drops the flag, which loses nothing it could act on, since the scores are the same either way on the same cache. A version bump was rejected for that reason: it would make every older build refuse every new file for a field none of them reads.
