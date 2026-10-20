# F1 Strategy Predictor

Predicts which Strategies F1 drivers are likely to be on, from historical races, practice running and live race data. Built in Python on FastF1.

## Development

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12 is pinned).

```sh
uv sync
uv run pytest
```

## Predict a race

```sh
uv run f1-strategy 2024 "Singapore Grand Prix"
```

Loads the weekend through FastF1 (cached in `.cache/fastf1`), makes every driver's Pre-race Prediction, compares it with the Strategies they actually ran, and prints a per-driver table followed by the race summary. `notebooks/end_to_end_real_race.ipynb` does the same step by step.

Real-data tests are marked `slow`; skip them with `uv run pytest -m "not slow"`.
