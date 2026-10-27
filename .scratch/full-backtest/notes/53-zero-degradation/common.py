"""Ticket 53 scratch: Tuning / Held-out scores from saved results, also on races scored by both runs."""
import os
import json, glob, sys
from pathlib import Path
HERE = Path(os.environ.get("T53_DATA", "/tmp/t53-data"))  # pickles and results, outside the repo
base = json.load(open("results/backtest/2026-10-27_baseline-v3.json"))
def idx(d): return {(r["season"], r["event"]): r for r in d["races"]}
B = idx(base)
def tot(rs):
    n = sum(r["summary"]["scoreable_drivers"] for r in rs); t1 = sum(r["summary"]["top_1_credit"] for r in rs)
    t3 = sum(r["summary"]["top_3_credit"] for r in rs); h = sum(r["summary"]["stop_window_hits"] for r in rs); s = sum(r["actual_stops"] for r in rs)
    return n, t1, t3, h, s
print("| Variant | Tuning top-1 | Tuning top-3 | Tuning hits | Tuning top-3, common races (Δ pp) | 2025 top-1 | 2025 top-3 | 2025 hits | races |")
for f in sorted(glob.glob(str(HERE / "results/*.json"))):
    name = Path(f).stem.split("_t53-")[1]
    V = idx(json.load(open(f)))
    tv = [r for k, r in V.items() if k[0] <= 2024]; hv = [r for k, r in V.items() if k[0] == 2025]
    n, t1, t3, h, s = tot(tv); hn, h1, h3, hh, hs = tot(hv)
    common = [k for k in V if k in B and k[0] <= 2024]
    cn, _, c3v, _, _ = tot([V[k] for k in common]); _, _, c3b, _, _ = tot([B[k] for k in common])
    print(f"| {name} | {t1:.2f}/{n} ({100*t1/n:.2f}%) | {t3:.2f}/{n} ({100*t3/n:.2f}%) | {h}/{s} | {100*c3v/cn:.2f}% vs {100*c3b/cn:.2f}% ({100*(c3v-c3b)/cn:+.2f}) | {100*h1/hn:.2f}% | {100*h3/hn:.2f}% | {hh}/{hs} | {len(V)} |")
