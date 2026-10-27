"""Ticket 53 scratch: per (race, team, Compound) practice fits with noise estimates,
compared with the same race's measured wear (fuel.pkl). Evaluation only."""
import os
import pickle, json, sys
from collections import defaultdict, Counter
from pathlib import Path
from statistics import fmean, median
import numpy as np
from f1_strategy.run_classifier import classify
from f1_strategy.settings import Settings

HERE = Path(os.environ.get("T53_DATA", "/tmp/t53-data"))  # pickles and results, outside the repo
W = pickle.load(open(HERE / "weekends.pkl", "rb"))
F = pickle.load(open(HERE / "fuel.pkl", "rb"))
base = json.load(open("results/backtest/2026-10-27_baseline-v3.json"))
scored = {(r["season"], r["event"]) for r in base["races"]}
S = Settings()

def fit(runs):
    sxy = sxx = 0.0; n = 0; resid = []
    for run in runs:
        ma = fmean(l.tyre_age for l in run); mt = fmean(l.lap_time for l in run)
        for l in run:
            sxy += (l.tyre_age - ma) * (l.lap_time - mt); sxx += (l.tyre_age - ma) ** 2
        n += len(run)
    if sxx <= 0: return None
    b = sxy / sxx
    for run in runs:
        ma = fmean(l.tyre_age for l in run); mt = fmean(l.lap_time for l in run)
        resid += [(l.lap_time - mt) - b * (l.tyre_age - ma) for l in run]
    dof = max(1, n - len(runs) - 1)
    se = (sum(r * r for r in resid) / dof) ** 0.5 / sxx ** 0.5
    return b, se, n

recs = []
for key, w in W.items():
    if key not in scored: continue
    pre = w.pre_race
    cl = classify(pre, S)
    for kind, runs in (("long_runs", cl.long_runs), ("push_laps", cl.push_lap_groups)):
        by = defaultdict(list); sess = defaultdict(Counter)
        # session of each run: find by identity
        run_sess = {}
        for s in pre.sessions:
            ids = {id(l) for l in s.laps}
            for r in runs:
                if id(r[0]) in ids: run_sess[id(r)] = s.name
        for r in runs:
            t = pre.teams.get(r[0].driver)
            if t is None: continue
            by[(t, r[0].compound.name)].append(r); sess[(t, r[0].compound.name)][run_sess.get(id(r), "?")] += len(r)
        for (t, c), rr in by.items():
            f = fit(rr)
            if f is None: continue
            b, se, n = f
            ages = [l.tyre_age for r in rr for l in r]
            recs.append(dict(season=key[0], event=key[1], circuit=pre.circuit, kind=kind, team=t, compound=c,
                             slope=b, se=se, n=n, runs=len(rr), maxlen=max(len(r) for r in rr),
                             sessions=dict(sess[(t, c)]), age_span=max(ages) - min(ages),
                             race_F=F.get(key, {}).get("F"), race_deg=F.get(key, {}).get("deg", {}).get(c)))
pickle.dump(recs, open(HERE / "diag.pkl", "wb"))

def pct(a): return f"{100*a:.0f}%"
for kind in ("long_runs", "push_laps"):
    for src, ss in (("FastF1 2022", (2022,)), ("OpenF1 2023-25", (2023, 2024, 2025))):
        R = [r for r in recs if r["kind"] == kind and r["season"] in ss]
        raw = np.array([r["slope"] + 0.03 for r in R]); z = np.array([(r["slope"] + 0.03) / r["se"] if r["se"] > 0 else 0 for r in R])
        print(f"\n## {kind} {src}: fits {len(R)}, raw(+0.03)<=0 {pct((raw<=0).mean())}, median raw {np.median(raw):.3f}, median n {np.median([r['n'] for r in R])}, median SE {np.median([r['se'] for r in R]):.3f}")
        print(f"   of the <=0 fits: z>-1 (within 1 SE of zero or positive) {pct((z[raw<=0]>-1).mean())}, z<-2 (significantly negative) {pct((z[raw<=0]<-2).mean())}")
        for c in ("SOFT", "MEDIUM", "HARD"):
            RC = [r for r in R if r["compound"] == c]
            if not RC: continue
            rawc = np.array([r["slope"] + 0.03 for r in RC])
            print(f"   {c}: {len(RC)} fits, <=0 {pct((rawc<=0).mean())}, median raw slope (no fuel) {np.median([r['slope'] for r in RC]):.3f}")
        # by lap count
        for lo, hi in ((0, 6), (6, 10), (10, 20), (20, 999)):
            RN = [r for r in R if lo <= r["n"] < hi]
            if RN:
                print(f"   n in [{lo},{hi}): {len(RN)} fits, <=0 {pct(np.mean([r['slope']+0.03<=0 for r in RN]))}, median SE {np.median([r['se'] for r in RN]):.3f}")
        if kind == "long_runs":
            for sname in ("FP1", "FP2", "FP3", "Sprint", "S", "SQ", "Q"):
                RS = [r for r in R if list(r["sessions"]) == [sname]]
                if RS:
                    print(f"   only {sname}: {len(RS)} fits, <=0 {pct(np.mean([r['slope']+0.03<=0 for r in RS]))}, median slope {np.median([r['slope'] for r in RS]):.3f}")
        # implied correction: race_deg - practice slope (per fit, where race has the compound)
        imp = [r["race_deg"] - r["slope"] for r in R if r["race_deg"] is not None and abs(r["race_F"]) < 0.2]
        print(f"   implied correction (race joint-model deg - practice slope): median {np.median(imp):.3f} IQR {np.percentile(imp,25):.3f}..{np.percentile(imp,75):.3f}  (n={len(imp)})")
