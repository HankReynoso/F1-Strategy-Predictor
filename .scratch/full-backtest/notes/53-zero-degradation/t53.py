"""Ticket 53 scratch harness (not production code).

- `make_team_degradation(**knobs)`: a parametrised copy of
  `degradation.team_degradation`; with no knobs it is the production function.
- `run(variant, label)`: offline Backtest over the pickled 2022-2025 weekends
  with `predictor.team_degradation` patched, saved to the scratchpad, plus the
  per-driver tables tickets 52, 53 and 54 use.
"""
from __future__ import annotations

import os

import json
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

import f1_strategy.backtest as bt
import f1_strategy.predictor as pr
from f1_strategy.backtest import RaceSpec, run_backtest
from f1_strategy.backtest_io import RunMetadata, save_backtest_result
from f1_strategy.degradation import (
    DegradationEstimate,
    DegradationSource as DS,
    _fit_by_team_compound,
    _weighted_mean,
)
from f1_strategy.run_classifier import classify
from f1_strategy.scorer import compare
from f1_strategy.settings import Settings
from f1_strategy.weekend import DRY_COMPOUNDS, Compound

HERE = Path(os.environ.get("T53_DATA", "/tmp/t53-data"))  # pickles and results, outside the repo
TUNING = (2022, 2023, 2024)
_WEEKENDS = None


def weekends():
    global _WEEKENDS
    if _WEEKENDS is None:
        _WEEKENDS = pickle.load(open(HERE / "weekends.pkl", "rb"))
    return _WEEKENDS


# Per-call raw log for diagnostics: (team, compound) -> dict
RAW_LOG: list[dict] = []


def make_team_degradation(
    fe_lr=0.03,
    fe_pl=0.03,
    fe_hist=0.03,
    use_push_laps=True,
    k=None,
    floor=None,              # dict Compound -> min rate, or None (0.0)
    neg_as_missing=False,    # team raw <= 0 → treated as no own data
    field_clamp_inputs=False,
    hist_min_stints=0,       # ticket 47-style minimum for Circuit History
    hist_floor=None,         # min rate for history when used
    monotone=False,          # enforce S >= M >= H per team after blending
    shrink_to_history=False, # shrink target: Circuit History when available
    min_own_laps=0,          # own fit needs at least this many laps
    fe_sprint=None,          # fuel effect for sprint-race Long Runs (session 'S')
    drop_quali=False,        # ignore Q/SQ sessions for Degradation
    field_monotone=False,    # PAVA on the field-level fallbacks too
    log=False,
):
    """Production `team_degradation` with knobs; defaults reproduce it."""

    def team_degradation(pre_race, settings):
        kk = settings.degradation_shrinkage_laps if k is None else k
        import dataclasses
        pr_ = pre_race
        if fe_sprint is not None or drop_quali:
            sess = []
            for s_ in pre_race.sessions:
                if drop_quali and s_.name in ("Q", "SQ"):
                    continue
                if fe_sprint is not None and s_.name == "S":
                    tilt = fe_sprint - fe_lr
                    s_ = dataclasses.replace(s_, laps=tuple(dataclasses.replace(l, lap_time=l.lap_time + tilt * l.tyre_age) for l in s_.laps))
                sess.append(s_)
            pr_ = dataclasses.replace(pre_race, sessions=tuple(sess))
        classified = classify(pr_, settings)
        team_lr = _fit_by_team_compound(classified.long_runs, pre_race.teams, fe_lr)
        team_pl = (
            _fit_by_team_compound(classified.push_lap_groups, pre_race.teams, fe_pl)
            if use_push_laps
            else {}
        )
        team_raw = {}
        for key, (rate, n) in team_pl.items():
            team_raw[key] = (rate, n, DS.PUSH_LAPS)
        for key, (rate, n) in team_lr.items():
            team_raw[key] = (rate, n, DS.LONG_RUNS)
        if min_own_laps:
            team_raw = {key: v for key, v in team_raw.items() if v[1] >= min_own_laps}
        if neg_as_missing:
            team_raw = {key: v for key, v in team_raw.items() if v[0] > 0}

        hist = {}
        for c, h in pre_race.historical_degradation.items():
            if h.stint_count < hist_min_stints:
                continue
            rate = h.rate + (fe_hist - 0.03)
            if hist_floor is not None:
                rate = max(rate, hist_floor.get(c, 0.0))
            hist[c] = rate

        def clampin(samples):
            return [(max(0.0, r), n) for r, n in samples] if field_clamp_inputs else samples

        resolved = {}
        for c in DRY_COMPOUNDS:
            fa = _weighted_mean(clampin([(r, n) for (_, cc), (r, n, _) in team_raw.items() if cc == c]))
            if fa is not None:
                resolved[c] = (fa, DS.FIELD_AVERAGE)
            elif c in hist:
                resolved[c] = (hist[c], DS.CIRCUIT_HISTORY)
            else:
                i = DRY_COMPOUNDS.index(c)
                if i and DRY_COMPOUNDS[i - 1] in resolved:
                    resolved[c] = (resolved[DRY_COMPOUNDS[i - 1]][0], DS.NEXT_SOFTER_BOUND)

        if field_monotone:
            cs = [c for c in DRY_COMPOUNDS if c in resolved]
            vals = _pava_nonincreasing([resolved[c][0] for c in cs])
            for c, v in zip(cs, vals):
                resolved[c] = (v, resolved[c][1])
        result = {}
        for team in set(pre_race.teams.values()):
            per = {}
            for c in DRY_COMPOUNDS:
                own = team_raw.get((team, c))
                others = clampin([(r, n) for (t, cc), (r, n, _) in team_raw.items() if cc == c and t != team])
                target = _weighted_mean(others)
                if shrink_to_history and c in hist:
                    target = hist[c]
                if own is not None:
                    raw, n, src = own
                    blended = (n * raw + kk * target) / (n + kk) if target is not None else raw
                else:
                    if c not in resolved:
                        raise ValueError(f"no Degradation for {c}")
                    raw, n = None, 0
                    blended, src = resolved[c]
                fl = (floor or {}).get(c, 0.0)
                per[c] = [blended, src, raw, n, target]
                if log:
                    RAW_LOG.append(dict(season=pre_race.season, circuit=pre_race.circuit,
                                        team=team, compound=c.name, source=src.value,
                                        raw=raw, n=n, target=target, blended=blended))
            if monotone:
                # pool-adjacent-violators on (S, M, H): rates non-increasing
                vals = [per[c][0] for c in DRY_COMPOUNDS]
                vals = _pava_nonincreasing(vals)
                for c, v in zip(DRY_COMPOUNDS, vals):
                    per[c][0] = v
            result[team] = {
                c: DegradationEstimate(max((floor or {}).get(c, 0.0), v[0]), v[1])
                for c, v in per.items()
            }
        return result

    return team_degradation


def _pava_nonincreasing(vals):
    blocks = [[v, 1] for v in vals]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] < blocks[i + 1][0]:
            tot = blocks[i][0] * blocks[i][1] + blocks[i + 1][0] * blocks[i + 1][1]
            cnt = blocks[i][1] + blocks[i + 1][1]
            blocks[i:i + 2] = [[tot / cnt, cnt]]
            i = max(i - 1, 0)
        else:
            i += 1
    out = []
    for v, c in blocks:
        out += [v] * c
    return out


def run(team_degradation_fn, label, settings=None, save=True, captured=None):
    settings = settings or Settings()
    ws = weekends()
    specs = [RaceSpec(s, e) for (s, e) in ws]
    captured = {} if captured is None else captured
    real_predict = pr.predict

    def load(season, event):
        return ws[(season, event)]

    def capturing_predict(weekend, settings=None):
        p = real_predict(weekend, settings)
        captured[(weekend.pre_race.season, weekend.pre_race.circuit, weekend.pre_race.race_laps)] = (p, weekend)
        return p

    orig_td, orig_bp = pr.team_degradation, bt.predict
    pr.team_degradation = team_degradation_fn
    bt.predict = capturing_predict
    try:
        result = run_backtest(specs, load=load, settings=settings)
    finally:
        pr.team_degradation, bt.predict = orig_td, orig_bp
    if save:
        md = RunMetadata(label=label, run_at="2026-10-27T12:00:00+00:00",
                         code_commit="bfc7722", uncommitted_changes=True,
                         seasons_in_scope=(2022, 2023, 2024, 2025),
                         settings=settings, offline=True)
        save_backtest_result(result, HERE / "results", metadata=md)
    scored = {(r.season, r.circuit) for r in result.races}
    tables = per_driver_tables(captured, scored)
    return result, tables


def per_driver_tables(captured, scored):
    """Zero-rate table (53), stop counts (52), edge windows (54), split by season group."""
    out = {"tuning": defaultdict(Counter), "held_out": defaultdict(Counter)}
    for (season, circuit, laps), (preds, weekend) in captured.items():
        if (season, circuit) not in scored:
            continue
        g = out["tuning" if season in TUNING else "held_out"]
        comp = compare(preds, weekend)
        neutral = bool(weekend.race.neutralisations)
        for driver, p in preds.items():
            for c, e in p.team_degradation.items():
                g["rates"][e.source.value] += 1
                g["rates"]["ALL"] += 1
                if e.rate <= 0:
                    g["zero"][e.source.value] += 1
                    g["zero"]["ALL"] += 1
                g["rate_sum_" + c.name][e.source.value] += 0  # placeholder
            s = comp.scores[driver]
            if s.unscoreable:
                continue
            bucket = "neut" if neutral else "green"
            top = p.candidates[0].strategy.stops
            act = len(s.actual.stop_laps)
            g[f"top_{bucket}"][min(top, 3)] += 1
            g[f"act_{bucket}"][min(act, 4)] += 1
            g["credit"]["top1"] += s.top_1_credit
            g["credit"]["top3"] += s.top_3_credit
            g["credit"]["drivers"] += 1
            for stop_lap, w, hit in zip(s.actual.stop_laps, s.stop_windows, s.stop_window_hits):
                width = w.last_lap - w.first_lap + 1
                edge = w.first_lap <= 6 or w.last_lap >= laps - 5
                kind = "interior" if not edge else ("edge<20" if width < 20 else "edge>=20")
                g["win_n"][kind] += 1
                g["win_hit"][kind] += int(hit)
                g["win_n"]["ALL"] += 1
                g["win_hit"]["ALL"] += int(hit)
                g["width"]["sum"] += width
            g["stops"]["actual"] += len(s.actual.stop_laps)
            g["stops"]["hits"] += sum(s.stop_window_hits)
    return out


def summarise(tables, name=""):
    lines = [f"== {name}"]
    for grp in ("tuning", "held_out"):
        g = tables[grp]
        z = g["zero"]; r = g["rates"]
        zt = ", ".join(f"{s}:{z[s]}/{r[s]}" for s in ("push_laps", "field_average", "circuit_history", "long_runs", "next_softer_bound", "ALL"))
        lines.append(f" [{grp}] zero {zt} ({100*z['ALL']/max(1,r['ALL']):.1f}%)")
        c = g["credit"]
        lines.append(f"   top1 {c['top1']:.2f} ({100*c['top1']/c['drivers']:.2f}%) top3 {c['top3']:.2f} ({100*c['top3']/c['drivers']:.2f}%) of {c['drivers']}; hits {g['stops']['hits']}/{g['stops']['actual']}")
        for b in ("green", "neut"):
            t = g[f"top_{b}"]; a = g[f"act_{b}"]
            lines.append(f"   {b}: actual 1/2/3/4+ {a[1]}/{a[2]}/{a[3]}/{a[4]}  top pick 1/2/3 {t[1]}/{t[2]}/{t[3]}")
        n, h = g["win_n"], g["win_hit"]
        lines.append("   windows " + ", ".join(f"{k} {h[k]}/{n[k]}" for k in ("interior", "edge<20", "edge>=20", "ALL"))
                     + f"; mean width {g['width']['sum']/max(1,n['ALL']):.1f}")
    return "\n".join(lines)


def tables_json(tables):
    return {g: {k: dict(v) for k, v in t.items()} for g, t in tables.items()}


if __name__ == "__main__":
    res, tabs = run(make_team_degradation(), "t53-default")
    print(summarise(tabs, "default"))
