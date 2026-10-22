# F1 Strategy Predictor

Predicts which Strategies F1 drivers are likely to be on, from historical races, practice running and live race data. Built in Python on FastF1.

## Development

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12 is pinned).

```sh
uv sync
uv run pytest
```

Real-data tests are marked `slow`; skip them with `uv run pytest -m "not slow"`.

## Predict a race

```sh
uv run f1-strategy 2024 "Singapore Grand Prix"
```

Loads the weekend through FastF1 (cached in `.cache/fastf1`), makes every driver's Pre-race Prediction, compares it with the Strategies they actually ran, and prints a per-driver table followed by the race summary. `notebooks/end_to_end_real_race.ipynb` does the same step by step.

## Run a full Backtest

Backtests run Pre-race Predictions with default settings over every race in scope, score each one against the actual race, and print a Backtest Result (headline scores, breakdowns, Excluded Races). Full runs happen on your laptop so the FastF1 cache persists between runs.

### First full run (laptop, cold cache)

The baseline Backtest covers the whole 2022–2025 Regulation Era with default settings:

```sh
uv run f1-strategy backtest 2022 2023 2024 2025 --label baseline
```

What to expect on your laptop with an empty `.cache/fastf1`:

- **Download cost (one-off).** The first full run downloads every race weekend through FastF1. Measured in a cloud session, a cold race weekend takes ~42 s and a cached one ~4 s (ticket 02). That is ~17 min of downloads per season on a cold cache, so a four-season cold run spends **~1 h on FastF1 downloads** end-to-end. Later runs reuse the on-disk cache and finish in a few minutes.
- **Compute cost.** The predict/compare loop itself is fast (~1 s per race on cached data), so cached runs over the full era take **~2–3 min** after the downloads are done.
- **Output.** Progress for each race goes to stderr; the formatted Backtest Result goes to stdout. The result shows the pooled green-race headline, race-averaged versions, Neutralised-only and all-races figures, breakdowns by season / circuit / sprint vs conventional, Tuning Seasons vs Held-out Season, Degradation source counts, and the Excluded Races list.
- **Where it is saved.** With `--label baseline`, two files land in `results/backtest/` (the folder is created on first save):
  - `<YYYY-MM-DD>_baseline.json` — the machine-readable Backtest Result that the compare command reads.
  - `<YYYY-MM-DD>_baseline.md` — the readable summary for GitHub.
  Both record the run's label, date and time, settings, code commit (plus an uncommitted-changes flag), seasons in scope and Held-out Season (ADR-0005).

### Running a Backtest over chosen seasons

Pass whichever seasons you want. Omit `--label` to print without saving:

```sh
uv run f1-strategy backtest 2024                   # single season, no save
uv run f1-strategy backtest 2024 --label spot-check
uv run f1-strategy backtest 2022 2023 2024 2025 --label baseline
```

Other flags: `--no-save` forces print-only even when `--label` is given; `--results-dir` points saves elsewhere (default `results/backtest`).

### After the run: label, commit and push

With `--label baseline` the save already names the files `<YYYY-MM-DD>_baseline.{json,md}`, which is the label the first baseline run should use. Commit and push both files so later tuned runs can compare against them:

```sh
git add results/backtest/<YYYY-MM-DD>_baseline.json results/backtest/<YYYY-MM-DD>_baseline.md
git commit -m "Baseline Backtest Result, 2022-2025 full era"
git push
```

The data file is scores only (no raw timing data), so it stays small enough to commit.

## Run the Smoke Set

The Smoke Set is a six-race subset covering every path through the model: Singapore, Monza, Baku, Austin and Jeddah 2024 (reference / Historical Degradation / used-set fallback / sprint / Neutralised Race) plus Spain 2022 (pre-era Pit Loss, ADR-0004 exception). It runs anywhere — cloud session or laptop — in a couple of minutes once the cache is warm, and prints the Backtest Result without saving it.

```sh
uv run f1-strategy smoke
```

Use it to check nothing broke end to end before running a full Backtest. On a cold cache in a cloud session the Smoke Set is dominated by the ~42 s cold-download cost per race weekend (ticket 02); on a warm cache it finishes in a few seconds.

## Compare two Backtest Results

Once you have a saved baseline and a saved tuned run, compare them:

```sh
uv run f1-strategy compare \
  results/backtest/<earlier>_baseline.json \
  results/backtest/<later>_tuned.json
```

The compare prints every headline score and breakdown as before/after/change in percentage points, the biggest-moving races in each direction, and warnings when the two runs don't cover the same races, Excluded Races, Tuning Seasons / Held-out Season, or when a race's Pit Loss flipped between measured and estimated.
