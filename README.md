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

- **Download cost (one-off).** The first full run downloads every race weekend through FastF1. Measured in a cloud session, a cold race weekend takes ~42 s and a cached one ~4 s (ticket 02). That is ~17 min of downloads per season on a cold cache, so the four-season transfer itself takes **~1 h** end-to-end. Later runs reuse the on-disk cache; run them with `--offline` (below) so they finish in minutes.
- **FastF1 rate limit.** FastF1 3.8 allows at most **500 uncached API calls per hour** across all its data sources and raises `RateLimitExceededError` beyond that (sliding one-hour window). A cold-cache weekend load spends roughly 50 of those calls between the race itself and the past-season pulls for Pit Loss and Historical Degradation, so after about nine weekends the limit is hit. The Backtest waits out the hour and resumes, with a message to stderr naming roughly when it will resume (ticket 17). On a cold cache the baseline Backtest therefore takes **~10 h wall-clock**: around nine 1-hour waits with 10 min of transfers between them. The run can be left unattended — it never turns a rate-limit hit into an Excluded Race. **Online warm-cache runs can still wait:** FastF1's request cache treats some saved responses (Ergast/Jolpica results, laps, qualifying) as stale after 12 hours and re-requests them, and each re-request counts toward the limit, so a full online re-run can stop for an hour at a time (ticket 36). Use `--offline` for re-runs.
- **Compute cost.** The predict/compare loop itself is fast (~1 s per race on cached data). A full four-season `--offline` run on the warm laptop cache took **~5 min** wall-clock with no network requests (ticket 36, 2026-10-27).
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

Other flags: `--no-save` forces print-only even when `--label` is given; `--results-dir` points saves elsewhere (default `results/backtest`); `--offline` reads saved data only (next section).

### Offline or online

Every command (`backtest`, `smoke` and the single-race command) runs **online** by default and takes `--offline`:

```sh
uv run f1-strategy backtest 2022 2023 2024 2025 --offline --label tuned-run
uv run f1-strategy smoke --offline
```

- **Online** fetches anything not yet downloaded. Use it for the first run on a new machine, for new races, and whenever the cache is cold. It is subject to FastF1's 500-per-hour limit, including on a warm cache (above).
- **Offline** reads only `.cache/fastf1` and `.cache/openf1` and never contacts FastF1 or OpenF1, so it never waits on a rate limit. Use it for every re-run on data you already have, such as tuning comparisons. On the same cache its results are identical to an online run's: the Smoke Set printed byte-identical results both ways (ticket 36).
- Anything an offline run needs but doesn't have is reported, never skipped silently. A race it can't build is an Excluded Race, `not downloaded (offline run)`. A past race or session it can't read is a Data Quality Warning saying `not downloaded`. The 2018–2020 seasons, which the timing archive refuses without an F1 TV login (ADR-0006), keep their archive reason both ways. If a run reports something as not downloaded, run it once online to fetch it.
- A saved Backtest Result records which mode it ran in (`offline` in the data file, a `Data:` line in the summary).

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

Use it to check nothing broke end to end before running a full Backtest. On a cold cache in a cloud session the Smoke Set is dominated by the ~42 s cold-download cost per race weekend (ticket 02); on a warm cache `smoke --offline` finishes in under 10 s (an online run on the same cache takes ~35 s, mostly Spain 2022's 2018–2020 requests that the archive refuses and FastF1 never caches).

## Compare two Backtest Results

Once you have a saved baseline and a saved tuned run, compare them:

```sh
uv run f1-strategy compare \
  results/backtest/<earlier>_baseline.json \
  results/backtest/<later>_tuned.json
```

The compare prints every headline score and breakdown as before/after/change in percentage points, the biggest-moving races in each direction, and warnings when the two runs don't cover the same races, Excluded Races, Tuning Seasons / Held-out Season, or when a race's Pit Loss flipped between measured and estimated.
