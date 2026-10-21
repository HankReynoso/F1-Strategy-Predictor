# 05: Saving Backtest Results

**What to build:** A full Backtest run is saved in the repo's results folder as a machine-readable data file plus a readable summary generated from it, both named by date and a short label. The Backtest Result records its label, run date and time, settings, code version (commit plus an uncommitted-changes flag), seasons in scope and Held-out Season. A saved result reads back identical. Smoke Set runs print but aren't saved unless asked. Results hold scores only, never raw timing data. See `../spec.md`.

**Blocked by:** 04 (Backtest breakdowns)

**Status:** done

- [x] A full run writes a data file and a readable summary, named by date and label
- [x] Label, date and time, settings, code version with uncommitted-changes flag, seasons in scope and Held-out Season are recorded
- [x] Saving then reading a Backtest Result gives an identical result
- [x] The readable summary shows the headline, breakdowns and Excluded Races
- [x] Runs can opt out of saving, and Smoke Set runs don't save by default
- [x] Tests go through the public save and read calls

## Implementation notes

**What was built (2026-10-21).**

- `src/f1_strategy/backtest_io.py`: a new module holding the two public
  calls `save_backtest_result(result, directory, *, metadata) -> SavedPaths`
  and `load_backtest_result(path) -> (BacktestResult, RunMetadata)`, plus
  the `RunMetadata` dataclass and two helpers (`default_run_at`,
  `detect_code_version`) the CLI uses to fill metadata at run time.
- `RunMetadata` carries: `label`, `run_at` (ISO 8601 UTC string),
  `code_commit`, `uncommitted_changes` (bool), `seasons_in_scope`
  (tuple[int, ...]) and the whole `Settings` object. The settings go in
  whole so a tuned run reads back with the same thresholds and the same
  Tuning/Held-out partition.
- Save writes two files side by side under `directory`:
  - `<YYYY-MM-DD>_<slug>.json` — the machine-readable data file.
  - `<YYYY-MM-DD>_<slug>.md` — the readable summary, built from a short
    metadata header plus `format_backtest(result)` inside a fenced code
    block (so GitHub preserves the alignment).
  The date comes from `metadata.run_at`; the slug collapses runs of
  unsafe characters in the label (spaces, slashes, …) into a single
  dash, so `"circuit tendency/v2"` becomes `circuit-tendency-v2` and no
  path separator smuggles through.
- The JSON file carries `"format_version": 1` at the top, then
  `metadata`, `races` (per-race records, every field on `RaceResult`
  including the new `estimated_pit_loss`), and `excluded`. Aggregates
  (headlines, race-averaged, breakdowns, Degradation source counts,
  Tuning/Held-out partition) are NOT stored — they're derivable from
  `races` + `Settings` (ticket 02 and ticket 04 already made every
  aggregate derivable from the per-race records), so `load_backtest_result`
  recomputes them with the same `_totals`/`_group_totals`/`_race_averaged`
  helpers `run_backtest` uses. An aggregation change benefits an old
  file without migrating it.
- Serialisation decisions, matching the review feedback at the end of
  ticket 04:
  - `DegradationSource` enum keys are serialised as their `.value`
    string (`"long_runs"`, `"field_average"`, …). JSON has no enum type;
    the string form is also what the formatter prints.
  - `ExclusionReason` is serialised as its `.value` string.
  - The sprint/conventional bool key on `by_sprint_weekend` isn't
    serialised at all — the breakdown is recomputed on load from each
    `RaceResult.is_sprint_weekend`. The formatter still turns `True`/
    `False` into `sprint`/`conventional`.
  - Circuit ordering in `by_circuit` isn't persisted; dict equality is
    order-independent in Python and the formatter sorts at print time.
- `load_backtest_result` guards on `format_version`: anything other than
  `1` is refused with a clear `ValueError`. Unknown keys inside a
  version-1 file are ignored, so a file written by an older build (one
  without `estimated_pit_loss`, say) still loads with the field
  defaulting to `False`. Settings carries the same shape: a key not on
  the current `Settings` is dropped on load.
- `RaceResult.estimated_pit_loss: bool = False` added to the dataclass
  so this ticket can serialise the field now. Ticket 07 will set it to
  `True` on the race weekends whose Pit Loss was estimated from pit lane
  length and speed limit; the field defaults to `False` so every
  existing test (and ticket 02's slow Singapore test) is unchanged. The
  save/load roundtrip test sets the flag on one race and asserts it
  reads back.
- `src/f1_strategy/cli.py`: Backtest mode gains three flags.
  - `--label LABEL`: when given, the run saves a Backtest Result data
    and summary file. When omitted, the run prints but does not save.
    This is how a Smoke Set run opts out of saving by default.
  - `--no-save`: force opt-out even when `--label` is given (useful for
    a quick ad-hoc check with a label).
  - `--results-dir DIR` (default `results/backtest`): where saved files
    land. Tests point this at `tmp_path`.
  The command tells the user on stderr where it wrote the files; the
  formatted result still goes to stdout, unchanged.
- `__init__.py`: new re-exports — `RunMetadata`, `SavedPaths`,
  `save_backtest_result`, `load_backtest_result`, `detect_code_version`,
  `default_run_at`.

**Decisions and alternatives rejected.**

- *JSON vs pickle vs YAML.* JSON. Python stdlib, human-readable, diffs
  on a PR, and the compare command (ticket 06) can load one with
  `json.loads` without any extra dependency. Pickle was rejected because
  a pickled `BacktestResult` ties the file to the current class graph
  and reader Python version; a reader on a future branch where
  `BacktestResult` has moved couldn't open old results. YAML was
  rejected because it adds a dependency for no benefit — the data is
  almost all numbers and short strings.
- *Store aggregates in the file, or recompute on load.* Recompute. Every
  aggregate was already derivable (ticket 02 and ticket 04's spec is
  explicit: "aggregates should be derivable from the per-race records,
  so a comparison or a future report can recompute them"). Storing them
  as well would open up drift between what the file says the headline
  is and what the per-race records sum to; the single source of truth
  stays the per-race records.
- *Format version.* `format_version: 1`, with a loader that refuses an
  unknown version and ignores unknown keys at version 1. Additive,
  defaulted fields (e.g. a new per-race flag) stay at version 1; a
  breaking change bumps the version. The alternative — never versioning
  and relying on duck-typing — was rejected because the saved files are
  committed to the repo and will outlive the code that wrote them.
- *One file vs two (data + summary).* Two. The data file powers the
  compare command and later tuning; the summary file reads on GitHub
  without anything checked out. Embedding the data in the markdown as
  a code block was rejected because the compare command would then
  have to parse markdown to reach the numbers.
- *Settings serialisation.* `dataclasses.asdict` with `tuning_seasons`
  cast to a list for JSON. On load, only keys the current `Settings`
  knows are passed to the constructor; the rest are dropped so an older
  file with a removed field still loads. The alternative — a hand-rolled
  per-field encoder — was rejected because it would need updating every
  time `Settings` grows a field, and every current field is JSON-safe.
- *Where to save by default.* `results/backtest/` at the repo root, so
  saved Backtest Results sit next to each other and compare easily.
  The spec says "repo's results folder" without naming one; the subdir
  under `results/` leaves room for other kinds of results next to it
  (per-race reports, say).
- *Smoke-Set opt-out mechanism.* `--label` is the opt-in: Smoke Set
  runs (ticket 08) won't pass one and so won't save. `--no-save` is an
  explicit opt-out for an ad-hoc run. The alternative — a dedicated
  `--save` flag — was rejected because the label is already required by
  the spec's naming rule, so a label is a natural opt-in signal.
- *Filename slugification.* A regex that collapses any run of unsafe
  characters into one dash, strips leading/trailing dashes, and falls
  back to `"unlabeled"` for an empty slug. Prevents a label with `/`
  from smuggling a path separator and keeps the filename legible.
- *`estimated_pit_loss` field placement.* On `RaceResult`, defaulted to
  `False`. Ticket 07 is being implemented in parallel and will set it
  to `True` on races whose Pit Loss came from the pit-lane-length
  estimate. Adding the field here with a default keeps both tickets'
  changes orthogonal and the save/load path ready for the flag; the
  rebase onto ticket 07 should be mechanical (same field, same default).
- *Readable summary built with `format_backtest`.* The ticket says the
  readable summary shows the headline, breakdowns and Excluded Races —
  which is exactly what `format_backtest` prints today. Reusing it
  avoids a second copy of the output that would drift from the printed
  one. The markdown wrapper is only a short header (label, run_at,
  commit, seasons in scope) plus a fenced code block containing the
  formatter's output.
- *Metadata on save, not on `BacktestResult`.* `RunMetadata` is passed
  to `save_backtest_result` and returned alongside `BacktestResult`
  from `load_backtest_result`, instead of being carried as a field on
  `BacktestResult`. Keeps `run_backtest` free of git subprocess calls
  and `datetime.now()` so the Backtest module itself stays testable
  without mocking either. The CLI builds the metadata where the save
  happens.

**Deviations from the ticket / spec.**

- The spec says the Backtest Result "records its label, run date and
  time, settings, code version, seasons in scope and Held-out Season".
  I split `BacktestResult` and `RunMetadata` into two objects: the
  result holds the scores and the per-race records; the metadata holds
  the run-level identity. The JSON file contains both; `load_backtest_result`
  returns both; a future user story that wants `result.metadata` can
  be served by having the save/load API return a pair (as it does
  today) or, if preferred, by adding an optional metadata field to
  `BacktestResult`. The ticket's acceptance criteria are all satisfied:
  the data file records everything the spec names, and reads back
  identical.

**Testing.**

- `tests/test_backtest_save_load.py` (13 tests, all through the public
  `save_backtest_result` / `load_backtest_result` pair with hand-built
  weekends and a fake loader):
  - saved → loaded Backtest Result is identical in every per-race
    record, every excluded race, and every aggregate (pooled, race-
    averaged, breakdowns, tuning/held-out, Degradation source counts,
    tuning_seasons/held_out_season).
  - `estimated_pit_loss=True` on one race round-trips; other races stay
    `False`.
  - data and summary filenames are `<date>_<label>.json`/`.md`.
  - a label with spaces and slashes is slugified safely.
  - metadata records label, run_at, code_commit, uncommitted_changes,
    seasons_in_scope and every settings field.
  - a non-default `Settings` (flipped tuning/held-out partition) round-
    trips.
  - the summary file carries headline, breakdowns and Excluded Races
    (every section `format_backtest` prints).
  - an unknown `format_version` is refused with a clear error.
  - `DegradationSource` keys and `ExclusionReason` are stored as
    `.value` strings.
  - the CLI without `--label` doesn't save; the CLI with `--label` saves
    data + summary files to `--results-dir`; `--no-save` overrides a
    label.
- Full fast suite: 124 passed (was 111 before this ticket; 13 new
  tests). No slow tests re-run as part of this ticket because save/load
  doesn't touch the FastF1 loader.

**Open questions, known limitations and follow-ups.**

- `RunMetadata` is a separate object from `BacktestResult`, so a caller
  that wants both must thread them together. If a later ticket wants
  `result.metadata` directly, the simplest route is an optional
  `metadata: RunMetadata | None = None` field on `BacktestResult` and
  one more line in `_rebuild_result` on load. No format change needed
  on disk.
- `detect_code_version` shells out to git. It falls back to
  `("unknown", True)` outside a git checkout, which is correct for a
  cloud session that doesn't have git installed but means a Backtest
  Result from such an environment is less traceable. The CLI could
  warn when the commit resolves to `"unknown"`; left as a follow-up.
- The summary file wraps `format_backtest`'s output in a fenced code
  block. If a later ticket wants proper markdown tables (so GitHub
  renders them), the formatter would need to grow a `markdown=True`
  path. Not blocking; the current output is plenty readable.
- `--results-dir` defaults to `results/backtest`. The repo doesn't have
  that folder yet; it will be created on first save. Ticket 09 (the
  first full baseline) is the first run to populate it.

**Review feedback to the user.**

- Ticket 06 (comparing) can load two files with `load_backtest_result`,
  then diff each `ScoreTotals` and `RaceAveraged` field pairwise. The
  only "scope" fields the compare should warn on when they differ are
  `metadata.seasons_in_scope`, the per-run `tuning_seasons`/
  `held_out_season`, and the set of races scored vs excluded.
- Ticket 07 (estimated Pit Loss): the per-race flag is already on
  `RaceResult.estimated_pit_loss` with a default of `False`, serialised
  and read back. Ticket 07's job is to set it to `True` on the races
  whose Pit Loss came from the pit-lane estimate; nothing in the save
  path needs changing. If ticket 07 also wants a run-level summary of
  how many races used an estimate, the compare and the formatter can
  derive it from the per-race flag (same shape as the Degradation
  source counts).
- Ticket 08 (Smoke Set) just doesn't pass `--label`, so Smoke Set runs
  print but don't save by default. If the Smoke Set command is a
  separate subcommand (`uv run f1-strategy smoke`), it should neither
  take `--label` nor save.
- Ticket 09 (first full baseline) will be the first saved Backtest
  Result in the repo: `uv run f1-strategy backtest 2022 2023 2024 2025
  --label baseline` writes
  `results/backtest/<YYYY-MM-DD>_baseline.json` and `.md`.
