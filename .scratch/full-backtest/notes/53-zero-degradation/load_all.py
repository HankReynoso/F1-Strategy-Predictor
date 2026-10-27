"""Ticket 53 scratch: load every 2022-2025 weekend offline once and pickle it."""
import pickle, sys
from f1_strategy.cli import _fastf1_load_and_list
OUT = sys.argv[1]
load, list_season = _fastf1_load_and_list(offline=True)
weekends = {}
for season in (2022, 2023, 2024, 2025):
    for spec in list_season(season):
        try:
            w = load(spec.season, spec.event)
        except Exception as e:
            weekends[(spec.season, spec.event)] = ("ERR", type(e).__name__, str(e)[:200])
            print("ERR", spec.season, spec.event, type(e).__name__, file=sys.stderr)
            continue
        weekends[(spec.season, spec.event)] = w
        print("ok", spec.season, spec.event, file=sys.stderr)
pickle.dump(weekends, open(OUT, "wb"))
