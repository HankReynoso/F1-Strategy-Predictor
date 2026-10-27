"""Ticket 53 scratch: estimate the per-lap 'fuel + track evolution' effect from each race.

Model per race: t = a_driver + b_compound - F*race_lap + d_c*tyre_age (OLS on clean
green laps, laps > stint median + 3 s dropped, race lap 1 dropped). F is identified
across Stints: fresh tyres late in the race are faster than fresh tyres early.
Also the production-style within-Stint slope (no fuel added) per compound."""
import os
import pickle, statistics as st
from pathlib import Path
import numpy as np

HERE = Path(os.environ.get("T53_DATA", "/tmp/t53-data"))  # pickles and results, outside the repo
races = pickle.load(open(HERE / "race_laps.pkl", "rb"))
rows = {}
for key, stints in races.items():
    recs = []
    within = {"SOFT": [], "MEDIUM": [], "HARD": []}
    for drv, comp, pts in stints:
        pts = [p for p in pts if p[0] > 1]
        if len(pts) < 4:
            continue
        med = st.median(p[2] for p in pts)
        pts = [p for p in pts if p[2] <= med + 3]
        # longest consecutive tyre-age run, as production does
        best, cur = [], []
        for p in pts:
            if cur and p[1] == cur[-1][1] + 1:
                cur.append(p)
            else:
                cur = [p]
            if len(cur) > len(best):
                best = list(cur)
        if len(best) >= 4:
            x = np.array([p[1] for p in best], float); y = np.array([p[2] for p in best])
            within[comp].append((np.polyfit(x, y, 1)[0], len(best)))
        for p in pts:
            recs.append((drv, comp, p[0], p[1], p[2]))
    if len(recs) < 100:
        continue
    drivers = sorted({r[0] for r in recs}); comps = ["SOFT", "MEDIUM", "HARD"]
    used = sorted({r[1] for r in recs}, key=comps.index)
    X = []; y = []
    for d, c, lap, age, t in recs:
        row = [1.0 if d == dd else 0.0 for dd in drivers]
        row += [1.0 if c == cc else 0.0 for cc in used[1:]]
        row += [-lap]
        row += [age if c == cc else 0.0 for cc in used]
        X.append(row); y.append(t)
    X = np.array(X); y = np.array(y)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    # one robust pass: drop residuals > 2 s
    res = y - X @ beta
    keep = np.abs(res) < 2
    beta, *_ = np.linalg.lstsq(X[keep], y[keep], rcond=None)
    nd = len(drivers) + len(used) - 1
    F = beta[nd]
    deg = {c: beta[nd + 1 + i] for i, c in enumerate(used)}
    w = {c: (sum(s * n for s, n in v) / sum(n for _, n in v) if v else None, sum(n for _, n in v)) for c, v in within.items()}
    rows[key] = dict(F=F, deg=deg, within=w, n=int(keep.sum()))
pickle.dump(rows, open(HERE / "fuel.pkl", "wb"))
Fs = [r["F"] for r in rows.values()]
print("races", len(rows), "F median %.3f IQR %.3f-%.3f" % (np.median(Fs), *np.percentile(Fs, [25, 75])))
for grp, ss in (("2022 FastF1", (2022,)), ("2023-25 OpenF1", (2023, 2024, 2025)), ("Tuning", (2022, 2023, 2024))):
    f = [r["F"] for k, r in rows.items() if k[0] in ss]
    print(f"  {grp}: n={len(f)} median F {np.median(f):.3f}")
for c in ("SOFT", "MEDIUM", "HARD"):
    jd = [r["deg"][c] for r in rows.values() if c in r["deg"]]
    ws = [r["within"][c][0] for r in rows.values() if r["within"][c][0] is not None]
    print(f"{c}: joint-model deg median {np.median(jd):.3f} ({sum(d<=0 for d in jd)}/{len(jd)} <=0);"
          f" within-stint raw slope median {np.median(ws):.3f}; +0.03 <=0 in {sum(s+0.03<=0 for s in ws)}/{len(ws)} races;"
          f" +F_race <=0 in {sum(r['within'][c][0]+r['F']<=0 for r in rows.values() if r['within'][c][0] is not None)}/{len(ws)}")
for k, r in sorted(rows.items()):
    print(k, "F=%.3f" % r["F"], {c: round(v, 3) for c, v in r["deg"].items()}, {c: (None if v[0] is None else round(v[0], 3), v[1]) for c, v in r["within"].items()})
