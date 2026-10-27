import os
import pickle, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
HERE = Path(os.environ.get("T53_DATA", "/tmp/t53-data"))  # pickles and results, outside the repo
L = pickle.load(open(HERE / "rawlog.pkl", "rb")); F = pickle.load(open(HERE / "fuel.pkl", "rb"))
D = pickle.load(open(HERE / "diag.pkl", "rb"))
circ = ["Baku", "Jeddah", "Melbourne", "Miami", "Monza", "Silverstone", "Zandvoort", "Austin"]
srcs = ["long_runs", "push_laps", "field_average", "circuit_history"]
print("| Circuit | Data | LR zero | PL zero | FA zero | CH zero | LR fits: median laps, raw<=0 & n<10 | Race-measured wear S/M/H (s/lap) | Race fuel+evolution F |")
for c in circ:
    for src, ss in (("FastF1", (2022,)), ("OpenF1", (2023, 2024, 2025))):
        R = [r for r in L if r["circuit"] == c and r["season"] in ss]
        if not R: continue
        cells = []
        for s in srcs:
            RS = [r for r in R if r["source"] == s]
            cells.append(f"{sum(r['blended']<=0 for r in RS)}/{len(RS)}" if RS else "–")
        lr = [d for d in D if d["circuit"] == c and d["season"] in ss and d["kind"] == "long_runs" and d["compound"] in ("SOFT","MEDIUM","HARD")]
        neg = [d for d in lr if d["slope"] + 0.03 <= 0]
        short = sum(d["n"] < 10 for d in neg)
        keys = [k for k in F if k[0] in ss and any(r["event"] == k[1] for r in R)]
        wear = []
        for cc in ("SOFT", "MEDIUM", "HARD"):
            v = [F[k]["deg"][cc] for k in keys if cc in F[k]["deg"] and abs(F[k]["F"]) < 0.2]
            wear.append(f"{np.median(v):.3f}" if v else "–")
        fs = [F[k]["F"] for k in keys if abs(F[k]["F"]) < 0.2]
        print(f"| {c} | {src} {sorted({r['season'] for r in R})} | " + " | ".join(cells) + f" | {np.median([d['n'] for d in lr]):.0f}, {short}/{len(neg)} of the <=0 fits | {' / '.join(wear)} | {np.median(fs):.3f} |")
