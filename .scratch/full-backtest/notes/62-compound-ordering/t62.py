"""Ticket 62 scratch (not production code): offline Backtests through ticket
53's harness, for the tables 53 recorded and the plain-versus-lap-weighted
mean choice. Reads `$T53_DATA/weekends.pkl` (made by 53's `load_all.py`) and
writes Backtest Results and `t62-tables.json` to `$T53_DATA`, outside the repo.

Variants:
- `before`: 53's copy of the pre-ticket-62 `team_degradation` (baseline-v3).
- `prototype`: 53's candidate A, `make_team_degradation(monotone=True)`.
- `production`: `degradation.team_degradation` as built in ticket 62.
- `lap-weighted`: production, but an inverted run shares its mean weighted
  by the lap-equivalents behind each estimate (own laps + shrinkage laps for
  a team's own fit; shrinkage laps for a field-level fallback).
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "53-zero-degradation"))
import t53  # noqa: E402

from f1_strategy import degradation as dg  # noqa: E402
from f1_strategy.degradation import DegradationEstimate, DegradationSource  # noqa: E402
from f1_strategy.run_classifier import classify  # noqa: E402
from f1_strategy.weekend import DRY_COMPOUNDS  # noqa: E402

HERE = Path(os.environ.get("T53_DATA", "/tmp/t53-data"))


def _weighted_pava(rates, weights):
    blocks = []  # (mean, weight, count)
    for r, w in zip(rates, weights):
        blocks.append((r, w, 1))
        while len(blocks) > 1 and blocks[-2][0] < blocks[-1][0]:
            (a, wa, ca), (b, wb, cb) = blocks[-2], blocks[-1]
            blocks[-2:] = [((a * wa + b * wb) / (wa + wb), wa + wb, ca + cb)]
    return [m for m, _, c in blocks for _ in range(c)]


def lap_weighted(pre_race, settings):
    classified = classify(pre_race, settings)
    fe = settings.fuel_effect_s_per_lap
    team_lr = dg._fit_by_team_compound(classified.long_runs, pre_race.teams, fe)
    team_pl = dg._fit_by_team_compound(classified.push_lap_groups, pre_race.teams, fe)
    team_raw = {}
    for key, (rate, n) in team_pl.items():
        team_raw[key] = (rate, n, DegradationSource.PUSH_LAPS)
    for key, (rate, n) in team_lr.items():
        team_raw[key] = (rate, n, DegradationSource.LONG_RUNS)
    field_fallback = dg._field_fallbacks(team_raw, pre_race.historical_degradation)
    k = settings.degradation_shrinkage_laps
    result = {}
    for team in set(pre_race.teams.values()):
        per = {}
        for c in DRY_COMPOUNDS:
            own = team_raw.get((team, c))
            others = [(r, n) for (t, cc), (r, n, _) in team_raw.items() if cc == c and t != team]
            fa = dg._weighted_mean(others)
            if own is not None:
                raw, n, src = own
                blended = (n * raw + k * fa) / (n + k) if fa is not None else raw
                per[c] = (blended, src, n + (k if fa is not None else 0))
                continue
            fb = field_fallback.get(c)
            if fb is None:
                raise ValueError(f"No Degradation for {c.name.title()}")
            per[c] = (fb[0], fb[1], k)
        vals = _weighted_pava([per[c][0] for c in DRY_COMPOUNDS], [max(per[c][2], 1e-9) for c in DRY_COMPOUNDS])
        result[team] = {c: DegradationEstimate(max(0.0, v), per[c][1]) for c, v in zip(DRY_COMPOUNDS, vals)}
    return result


VARIANTS = {
    "before": t53.make_team_degradation(),
    "prototype": t53.make_team_degradation(monotone=True),
    "production": dg.team_degradation,
    "lap-weighted": lap_weighted,
}

if __name__ == "__main__":
    out = HERE / "t62-tables.json"
    allt = json.load(open(out)) if out.exists() else {}
    for name in sys.argv[1:] or list(VARIANTS):
        _, tabs = t53.run(VARIANTS[name], "t62-" + name)
        print(t53.summarise(tabs, name), flush=True)
        allt[name] = t53.tables_json(tabs)
        json.dump(allt, open(out, "w"))


def soft_ending_one_stops(name):
    """Tuning-Season drivers whose top pick is H → S or M → S (ticket 53: 338)."""
    from collections import Counter

    from f1_strategy.scorer import compare

    captured = {}
    result, _ = t53.run(VARIANTS[name], "x", save=False, captured=captured)
    scored = {(r.season, r.circuit) for r in result.races}
    top = Counter()
    for (season, circuit, _), (preds, weekend) in captured.items():
        if (season, circuit) not in scored or season not in t53.TUNING:
            continue
        for driver, score in compare(preds, weekend).scores.items():
            if not score.unscoreable:
                top["-".join(c.value for c in preds[driver].candidates[0].strategy.compounds)] += 1
    return top["H-S"], top["M-S"], sum(top.values())
