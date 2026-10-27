# Ticket 53 scratch scripts

Exploratory code for ticket 53's investigation. Not production code, and not imported by `src/`. Every script reads saved data only (offline) and writes its pickles and Backtest Results to `$T53_DATA` (default `/tmp/t53-data`), outside the repo. Run from the repo root with `uv run python <script>`, in this order:

1. `load_all.py $T53_DATA/weekends.pkl`: loads every 2022–2025 weekend through the offline router once (about 90 s).
2. `race_laps.py`: clean race-Stint laps of each weekend's own race, for evaluation only.
3. `fuel.py`: per race, the non-tyre lap-time trend (fuel burn plus track evolution) and the race-measured wear per Compound.
4. `diag.py`, `diag2.py`, `circuits.py`: per-source diagnosis of zero rates.
5. `variants.py`, `variants2.py`: candidate fixes as offline Backtests (about 30 s each). `t53.py` holds the harness and the parametrised copy of `team_degradation`; with no knobs it reproduces baseline-v3 exactly.
6. `common.py`: Tuning and Held-out scores per variant, also on the races both runs scored. `why.py`: top-pick Compound sequences.

Compare a saved variant with the baseline:

```sh
uv run f1-strategy compare results/backtest/2026-10-27_baseline-v3.json $T53_DATA/results/2026-10-27_t53-<variant>.json
```
