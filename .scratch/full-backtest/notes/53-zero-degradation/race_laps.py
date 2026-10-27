"""Ticket 53 scratch: clean race-Stint laps (race lap, tyre age, lap time) for each
weekend's own race, offline, with the same cleaning rules as Historical Degradation
(no pit-in/out, no SC/VSC laps, no missing times). Evaluation only."""
import os
import pickle, sys
from pathlib import Path
import pandas as pd
from f1_strategy import fastf1_loader as ff, openf1_loader as of
from f1_strategy.cli import _fastf1_load_and_list
from f1_strategy.openf1_client import OpenF1Client
from f1_strategy.weekend import DRY_COMPOUNDS

HERE = Path(os.environ.get("T53_DATA", "/tmp/t53-data"))  # pickles and results, outside the repo
_fastf1_load_and_list(offline=True)  # sets FastF1 cache offline
client = OpenF1Client(cache_dir=Path(".cache/openf1"), offline=True)
weekends = pickle.load(open(HERE / "weekends.pkl", "rb"))
out = {}
for (season, event), w in weekends.items():
    stints = []
    if season >= 2023:
        rows = of._load_past_race_rows(client, season, event)
        n = of._race_laps_count(rows["session_result"], rows["session_key"])
        periods, _ = of._neutralisation_periods(rows["race_control"], n)
        neut = of._neutralised_lap_set(periods)
        pit_rows = rows["pit"] or of._pit_rows_from_stints(rows["stints"])
        laps = {}
        for r in rows["laps"]:
            laps.setdefault(int(r["driver_number"]), {})[int(r["lap_number"])] = r
        pits = {}
        for r in pit_rows:
            pits.setdefault(int(r["driver_number"]), set()).add(int(r["lap_number"]))
        for s in rows["stints"]:
            c = of._COMPOUND.get(str(s.get("compound", "")).upper())
            if c not in DRY_COMPOUNDS or s.get("lap_start") is None or s.get("lap_end") is None:
                continue
            d = int(s["driver_number"]); a0 = int(s.get("tyre_age_at_start") or 0)
            pts = []
            for ln in range(int(s["lap_start"]), int(s["lap_end"]) + 1):
                r = laps.get(d, {}).get(ln)
                if r is None or ln in pits.get(d, set()) or r.get("is_pit_out_lap") or ln in neut or r.get("lap_duration") is None:
                    continue
                pts.append((ln, ln - int(s["lap_start"]) + 1 + a0, float(r["lap_duration"])))
            stints.append((str(d), c.name, pts))
    else:
        sched, _ = ff._schedule(season)
        m = sched[(sched["EventName"].str.lower() == event.lower()) | (sched["Location"].str.lower() == event.lower())]
        race, reason = ff._load_session(season, int(m.iloc[0]["RoundNumber"]), "R", "x")
        df = race.laps
        for drv in df["Driver"].unique():
            dl = df[df["Driver"] == drv].sort_values("LapNumber")
            for _, sl in dl.groupby("Stint", sort=True):
                cr = sl["Compound"].dropna()
                if cr.empty:
                    continue
                c = ff._COMPOUND.get(str(cr.iloc[0]).upper())
                if c not in DRY_COMPOUNDS:
                    continue
                pts = []
                for _, lap in sl.iterrows():
                    if pd.isna(lap.get("LapTime")) or pd.isna(lap.get("TyreLife")):
                        continue
                    if not pd.isna(lap.get("PitInTime")) or not pd.isna(lap.get("PitOutTime")):
                        continue
                    if ff._lap_neutralisation_kind(str(lap.get("TrackStatus", "1"))) is not None:
                        continue
                    pts.append((int(lap["LapNumber"]), int(lap["TyreLife"]), lap["LapTime"].total_seconds()))
                stints.append((drv, c.name, pts))
    out[(season, event)] = stints
    print(season, event, len(stints), file=sys.stderr)
pickle.dump(out, open(HERE / "race_laps.pkl", "wb"))
