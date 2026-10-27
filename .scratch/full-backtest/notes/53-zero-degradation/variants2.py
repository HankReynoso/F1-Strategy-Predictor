"""Ticket 53 scratch: second batch, ordering combined with the other fixes."""
import os
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))  # t53 harness
import t53
from t53 import make_team_degradation as M
from f1_strategy.weekend import DRY_COMPOUNDS
HERE = Path(os.environ.get("T53_DATA", "/tmp/t53-data"))  # pickles and results, outside the repo
fl = lambda x: {c: x for c in DRY_COMPOUNDS}
V = {
    "race-fuel": M(fe_sprint=0.057, fe_hist=0.057),
    "drop-quali": M(drop_quali=True),
    "floor-0.02": M(floor=fl(0.02)),
    "mono+k-16": M(monotone=True, k=16),
    "mono+no-push": M(monotone=True, use_push_laps=False),
    "mono+fuel-0.057": M(monotone=True, fe_lr=0.057, fe_pl=0.057, fe_hist=0.057),
    "mono+race-fuel": M(monotone=True, fe_sprint=0.057, fe_hist=0.057),
    "mono+field-mono": M(monotone=True, field_monotone=True),
    "mono+floor-0.02": M(monotone=True, floor=fl(0.02)),
    "mono+floor-0.04": M(monotone=True, floor=fl(0.04)),
    "mono+k-16+race-fuel": M(monotone=True, k=16, fe_sprint=0.057, fe_hist=0.057),
    "mono+k-16+floor-0.02": M(monotone=True, k=16, floor=fl(0.02)),
}
names = sys.argv[1:] or list(V)
allt = json.load(open(HERE / "tables.json"))
for name in names:
    res, tabs = t53.run(V[name], "t53-" + name)
    print(t53.summarise(tabs, name), flush=True)
    allt[name] = t53.tables_json(tabs)
    json.dump(allt, open(HERE / "tables.json", "w"))
