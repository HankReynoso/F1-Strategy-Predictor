"""Ticket 53 scratch: why do higher rates lower top-3? Sequence-level comparison."""
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))  # t53 harness
import t53
from t53 import make_team_degradation as M
from f1_strategy.scorer import compare
for name, fn in (("base", M()), ("neg-as-missing", M(neg_as_missing=True)), ("monotone", M(monotone=True))):
    cap = {}
    res, _ = t53.run(fn, "x", save=False, captured=cap)
    scored = {(r.season, r.circuit) for r in res.races}
    act = Counter(); top = Counter(); cand = 0; plaus_rank = Counter(); n = 0; stopmatch = 0; setmatch = 0
    for (season, circ, laps), (preds, w) in cap.items():
        if (season, circ) not in scored or season not in t53.TUNING: continue
        comp = compare(preds, w)
        for d, s in comp.scores.items():
            if s.unscoreable: continue
            n += 1
            a = "-".join(c.value for c in s.actual.compounds); act[a] += 1
            t = preds[d].candidates[0].strategy; top["-".join(c.value for c in t.compounds)] += 1
            stopmatch += t.stops == len(s.actual.stop_laps)
            setmatch += set(t.compounds) == set(s.actual.compounds) and t.stops == len(s.actual.stop_laps)
            ranked = sorted(preds[d].candidates, key=lambda c: -c.probability)
            idx = next((i for i, c in enumerate(ranked) if c.strategy.compounds == s.actual.compounds), None)
            plaus_rank["not candidate" if idx is None else ("1-3" if idx < 3 else "4+")] += 1
    print(f"== {name} (Tuning, {n} drivers): top-pick stop count = actual {stopmatch} ({100*stopmatch/n:.0f}%), stops+compound set = actual {setmatch}")
    print("   actual rank:", dict(plaus_rank))
    print("   actual top seqs:", act.most_common(8))
    print("   top-pick seqs:  ", top.most_common(8))
