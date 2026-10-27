"""Ticket 53 scratch: per-source zero analysis against the same race's measured wear."""
import os
import pickle, json, sys
from collections import defaultdict, Counter
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))  # t53 harness
import t53
from f1_strategy.settings import Settings
HERE = Path(os.environ.get("T53_DATA", "/tmp/t53-data"))  # pickles and results, outside the repo
W = t53.weekends(); F = pickle.load(open(HERE / "fuel.pkl", "rb")); D = pickle.load(open(HERE / "diag.pkl", "rb"))
base = json.load(open("results/backtest/2026-10-27_baseline-v3.json"))
scored = {(r["season"], r["event"]) for r in base["races"]}
fn = t53.make_team_degradation(log=True)
t53.RAW_LOG.clear()
ev_of = {}
for key, w in W.items():
    if key not in scored: continue
    fn(w.pre_race, Settings()); ev_of[(w.pre_race.season, w.pre_race.circuit)] = key
L = t53.RAW_LOG
for r in L:
    k = ev_of[(r["season"], r["circuit"])]
    r["event"] = k[1]; fr = F.get(k); r["race_deg"] = fr["deg"].get(r["compound"]) if fr and abs(fr["F"]) < 0.2 else None
pickle.dump(L, open(HERE / "rawlog.pkl", "wb"))
# team-level (unique per team) zero by source
print("Team-level (one per team, not per driver) zero shares, baseline:")
for src in ("long_runs", "push_laps", "field_average", "circuit_history", "next_softer_bound"):
    R = [r for r in L if r["source"] == src]
    z = [r for r in R if r["blended"] <= 0]
    rd_z = [r["race_deg"] for r in z if r["race_deg"] is not None]
    rd_p = [r["race_deg"] for r in R if r["blended"] > 0 and r["race_deg"] is not None]
    print(f"  {src}: {len(z)}/{len(R)} zero; race's own measured wear on that Compound: median {np.median(rd_z) if rd_z else float('nan'):.3f} where zero vs {np.median(rd_p) if rd_p else float('nan'):.3f} where positive; race wear <=0.02 in {sum(x<=0.02 for x in rd_z)}/{len(rd_z)} zero cases")
# field-average composition
print("\nField average: inputs (other teams' raw fits) by source, and what removing Push Laps does")
fa = [r for r in L if r["source"] == "field_average"]
# recompute composition per weekend-compound
comp = defaultdict(lambda: Counter())
for r in L:
    if r["source"] in ("long_runs", "push_laps"):
        comp[(r["season"], r["circuit"], r["compound"])][r["source"]] += r["n"]
pl_share_zero = []; pl_share_pos = []
for r in fa:
    c = comp[(r["season"], r["circuit"], r["compound"])]
    s = c["push_laps"] / max(1, c["push_laps"] + c["long_runs"])
    (pl_share_zero if r["blended"] <= 0 else pl_share_pos).append(s)
print(f"  Push Lap share of field-average laps: median {np.median(pl_share_zero):.2f} where zero vs {np.median(pl_share_pos):.2f} where positive; all-Push-Lap field averages: {sum(s==1 for s in pl_share_zero)}/{len(pl_share_zero)} zero vs {sum(s==1 for s in pl_share_pos)}/{len(pl_share_pos)} positive")
# shrinkage: own raw positive but blended zero (pulled down), or own raw <=0
for src in ("long_runs", "push_laps"):
    R = [r for r in L if r["source"] == src]
    a = sum(1 for r in R if r["raw"] > 0 and r["blended"] <= 0)
    b = sum(1 for r in R if r["raw"] <= 0 and r["blended"] <= 0)
    c = sum(1 for r in R if r["raw"] <= 0 and r["blended"] > 0)
    tneg = sum(1 for r in R if r["target"] is not None and r["target"] <= 0)
    print(f"  {src}: own fit >0 but pulled to <=0 by a <=0 field average: {a}; own fit <=0 and stays <=0: {b}; own fit <=0 rescued by shrinkage: {c}; shrink target <=0: {tneg}/{len(R)}")
# Circuit history
print("\nCircuit History rates (team-level):")
H = [r for r in L if r["source"] == "circuit_history"]
for r in sorted(H, key=lambda r: (r["season"], r["circuit"], r["compound"])):
    pass
hc = Counter((r["season"], r["circuit"], r["compound"], round(r["blended"], 3), r["race_deg"] and round(r["race_deg"], 3)) for r in H)
for k, v in sorted(hc.items()):
    print("  ", k, "teams", v)
# per circuit, both sources
print("\nPer circuit (team-level zero share, all practice/field sources; race's own measured wear):")
pc = defaultdict(lambda: [0, 0, set()])
for r in L:
    k = (r["circuit"], "FastF1" if r["season"] == 2022 else "OpenF1")
    pc[k][1] += 1; pc[k][0] += r["blended"] <= 0; pc[k][2].add(r["season"])
for k, (z, n, ss) in sorted(pc.items()):
    print(f"  {k[0]:25s} {k[1]:7s} {z:3d}/{n:3d} ({100*z/n:3.0f}%) seasons {sorted(ss)}")
