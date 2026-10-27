"""Ticket 53 scratch: run candidate fixes as offline Backtests; print summary tables."""
import os
import json, pickle, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))  # t53 harness
import t53
from t53 import make_team_degradation as M
HERE = Path(os.environ.get("T53_DATA", "/tmp/t53-data"))  # pickles and results, outside the repo

V = {
    "base": M(),
    "no-push": M(use_push_laps=False),
    "fuel-0.057": M(fe_lr=0.057, fe_pl=0.057, fe_hist=0.057),
    "fuel-0.045": M(fe_lr=0.045, fe_pl=0.045, fe_hist=0.045),
    "fuel-0.07": M(fe_lr=0.07, fe_pl=0.07, fe_hist=0.07),
    "hist-fuel-0.057": M(fe_hist=0.057),
    "k-8": M(k=8),
    "k-16": M(k=16),
    "min-own-8": M(min_own_laps=8),
    "neg-as-missing": M(neg_as_missing=True),
    "monotone": M(monotone=True),
    "no-push+fuel-0.057": M(use_push_laps=False, fe_lr=0.057, fe_hist=0.057),
    "no-push+k-8": M(use_push_laps=False, k=8),
    "no-push+monotone": M(use_push_laps=False, monotone=True),
}
names = sys.argv[1:] or list(V)
allt = json.load(open(HERE / "tables.json")) if (HERE / "tables.json").exists() else {}
for name in names:
    res, tabs = t53.run(V[name], "t53-" + name)
    print(t53.summarise(tabs, name), flush=True)
    allt[name] = t53.tables_json(tabs)
    json.dump(allt, open(HERE / "tables.json", "w"))
