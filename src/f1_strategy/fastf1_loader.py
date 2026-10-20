"""Load a real race weekend from FastF1 into the race weekend description.

This is the only module that knows about FastF1. It turns an on-disk
FastF1 cache into the plain, project-owned race weekend description that
the predictor reads. Pit Loss for the circuit is measured from previous
seasons' races there, never from the race being predicted.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable

import fastf1
import pandas as pd

from .weekend import (
    Compound,
    Lap,
    NeutralisationPeriod,
    PreRaceInfo,
    RaceOutcome,
    RaceWeekend,
    Session,
    Stint,
)

_COMPOUND = {
    "SOFT": Compound.SOFT,
    "MEDIUM": Compound.MEDIUM,
    "HARD": Compound.HARD,
    "INTERMEDIATE": Compound.INTERMEDIATE,
    "WET": Compound.WET,
}

# FastF1's long session names → short identifiers used in `Session.name`.
_SESSION_SHORT_NAME = {
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
    "Qualifying": "Q",
    "Sprint": "S",
    "Sprint Qualifying": "SQ",
    "Sprint Shootout": "SS",
}

# A lap's TrackStatus concatenates every code seen during it (e.g. "124").
# Only SC (4) and VSC (6 deployed, 7 ending) neutralise; yellow (2) and
# red flag (5) do not.
_SC_STATUS = {"4"}
_VSC_STATUS = {"6", "7"}


def load_weekend(
    season: int,
    event: str,
    cache_dir: str | Path = ".cache/fastf1",
    pit_loss_min_season: int = 2022,
) -> RaceWeekend:
    """Load a FastF1 race weekend into the race weekend description.

    `event` is anything FastF1 accepts (official name or location name).
    `cache_dir` is the FastF1 on-disk cache; repeat loads come from it.
    `pit_loss_min_season` is the earliest season to draw pit-loss data from.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_dir))

    race = fastf1.get_session(season, event, "R")
    race.load(laps=True, telemetry=False, weather=False, messages=False)

    event_meta = race.event
    circuit = str(event_meta["Location"])
    is_sprint = str(event_meta["EventFormat"]) != "conventional"
    teams = _starters_and_teams(race)

    sessions = tuple(
        _load_pre_race_session(season, event, event_meta, i, drivers=set(teams))
        for i in range(1, 5)
    )
    sessions = tuple(s for s in sessions if s is not None)

    stints = _race_stints(race, drivers=set(teams))
    neutralisations = _neutralisation_periods(race)
    finishing_status = _finishing_status(race, drivers=set(teams))

    pit_loss = _pit_loss_at_circuit(
        circuit=circuit,
        race_season=season,
        min_season=pit_loss_min_season,
        cache_dir=cache_dir,
    )

    return RaceWeekend(
        pre_race=PreRaceInfo(
            circuit=circuit,
            season=season,
            race_laps=int(race.total_laps),
            is_sprint_weekend=is_sprint,
            sessions=sessions,
            teams=teams,
            pit_loss=pit_loss,
        ),
        race=RaceOutcome(
            stints=stints,
            neutralisations=neutralisations,
            finishing_status=finishing_status,
        ),
    )


def _starters_and_teams(race) -> dict[str, str]:
    results = race.results
    starters = results[results["GridPosition"].notna() & (results["GridPosition"] > 0)]
    return {
        str(row["Abbreviation"]): str(row["TeamName"])
        for _, row in starters.iterrows()
    }


def _load_pre_race_session(
    season: int,
    event: str,
    event_meta,
    index: int,
    drivers: set[str],
) -> Session | None:
    long_name = str(event_meta[f"Session{index}"])
    if long_name in ("", "None", "Race"):
        return None
    short_name = _SESSION_SHORT_NAME.get(long_name, long_name)
    try:
        session = fastf1.get_session(season, event, short_name)
        session.load(laps=True, telemetry=False, weather=False, messages=False)
    except Exception:
        return None

    laps = tuple(_laps_from(session, short_name, drivers))
    return Session(name=short_name, laps=laps)


def _laps_from(session, session_name: str, drivers: set[str]) -> Iterable[Lap]:
    df = session.laps
    if df is None or df.empty:
        return
    for _, row in df.iterrows():
        driver = str(row["Driver"])
        compound_raw = row.get("Compound")
        lap_time = row.get("LapTime")
        if pd.isna(lap_time) or compound_raw is None or pd.isna(compound_raw):
            # Skip rows that have no useful tyre or timing info.
            continue
        compound = _COMPOUND.get(str(compound_raw).upper())
        if compound is None:
            continue
        stint = row.get("Stint")
        tyre_age_raw = row.get("TyreLife")
        if pd.isna(tyre_age_raw):
            continue
        yield Lap(
            driver=driver,
            lap_number=int(row["LapNumber"]),
            lap_time=float(lap_time.total_seconds()),
            tyre_set=f"{driver}-{session_name}-stint{int(stint) if not pd.isna(stint) else 0}-{compound.value}",
            compound=compound,
            tyre_age=int(tyre_age_raw),
            new_when_fitted=bool(row.get("FreshTyre")),
            pit_in=not pd.isna(row.get("PitInTime")),
            pit_out=not pd.isna(row.get("PitOutTime")),
            neutralised=_lap_neutralisation_kind(str(row.get("TrackStatus", "1")))
            is not None,
        )


def _race_stints(race, drivers: set[str]) -> tuple[Stint, ...]:
    df = race.laps
    stints: list[Stint] = []
    if df is None or df.empty:
        return ()
    for driver in sorted(drivers):
        driver_laps = df[df["Driver"] == driver].sort_values("LapNumber")
        if driver_laps.empty:
            continue
        for stint_num, stint_laps in driver_laps.groupby("Stint", sort=True):
            compound_raw = stint_laps["Compound"].dropna()
            if compound_raw.empty:
                continue
            compound = _COMPOUND.get(str(compound_raw.iloc[0]).upper())
            if compound is None:
                continue
            start = int(stint_laps["LapNumber"].min())
            end = int(stint_laps["LapNumber"].max())
            stints.append(
                Stint(driver=driver, compound=compound, start_lap=start, end_lap=end)
            )
    return tuple(stints)


def _finishing_status(race, drivers: set[str]) -> dict[str, bool]:
    """True if the driver took the chequered flag (lapped or not).

    FastF1's `results.Status` is "Finished" for lead-lap finishers and
    "Lapped" (or "+N Lap(s)" in older FastF1 versions) for lapped
    finishers. Anything else — "Retired", "Disqualified", "Did not
    start", a crash reason, etc. — means they did not take the flag,
    including a driver classified after retiring in the last few laps.
    """
    results = race.results
    status: dict[str, bool] = {}
    for _, row in results.iterrows():
        driver = str(row["Abbreviation"])
        if driver not in drivers:
            continue
        raw = str(row["Status"])
        status[driver] = raw == "Finished" or raw == "Lapped" or raw.startswith("+")
    return status


def _neutralisation_periods(race) -> tuple[NeutralisationPeriod, ...]:
    """Group race track-status flags into SC/VSC periods, labelled by lap.

    Race laps are counted by the leader, so each lap's status is read from
    the first car to complete it. Other cars' laps straddle the leader's and
    would stretch periods (e.g. a crashed car's unfinished lap).
    """
    df = race.laps
    if df is None or df.empty:
        return ()
    completed = df[df["Time"].notna()]
    leader_laps = completed.loc[completed.groupby("LapNumber")["Time"].idxmin()]

    periods: list[NeutralisationPeriod] = []
    for _, row in leader_laps.sort_values("LapNumber").iterrows():
        lap = int(row["LapNumber"])
        kind = _lap_neutralisation_kind(str(row["TrackStatus"]))
        if kind is None:
            continue
        last = periods[-1] if periods else None
        if last and last.kind == kind and last.end_lap == lap - 1:
            periods[-1] = NeutralisationPeriod(kind, last.start_lap, lap)
        else:
            periods.append(NeutralisationPeriod(kind, lap, lap))
    return tuple(periods)


def _lap_neutralisation_kind(status: str) -> str | None:
    """TrackStatus codes seen on a lap → SC, VSC, or None."""
    codes = set(status)
    if codes & _SC_STATUS:
        return "SC"
    if codes & _VSC_STATUS:
        return "VSC"
    return None


def _pit_loss_at_circuit(
    circuit: str,
    race_season: int,
    min_season: int,
    cache_dir: str | Path,
) -> float:
    """Measure Pit Loss from previous seasons' races at the circuit.

    Raises `ValueError` if no previous-season data is available: the
    predictor would rather refuse than invent a Pit Loss from the race
    being predicted.
    """
    fastf1.Cache.enable_cache(str(cache_dir))
    weighted: list[tuple[float, float]] = []  # (median_loss_for_race, weight)
    for season in range(min_season, race_season):
        try:
            schedule = fastf1.get_event_schedule(season)
        except Exception:
            continue
        matches = schedule[schedule["Location"] == circuit]
        for _, row in matches.iterrows():
            try:
                past = fastf1.get_session(season, int(row["RoundNumber"]), "R")
                past.load(laps=True, telemetry=False, weather=False, messages=False)
                if not hasattr(past, "_laps"):
                    # FastF1's `load` logs and continues when the live-timing
                    # API refuses the data (e.g. older seasons behind a 403).
                    # The session is then unusable for Pit Loss.
                    continue
                losses = list(_pit_losses_in(past))
            except Exception:
                continue
            if not losses:
                continue
            losses.sort()
            median = losses[len(losses) // 2]
            weight = 0.5 ** (race_season - season - 1)
            weighted.append((median, weight))
    if not weighted:
        raise ValueError(
            f"no previous seasons' races at {circuit!r} were available to measure "
            f"Pit Loss from (looked at {min_season}..{race_season - 1})"
        )
    total_weight = sum(w for _, w in weighted)
    return sum(m * w for m, w in weighted) / total_weight


def _pit_losses_in(race) -> Iterable[float]:
    """Per-pit-stop time loss from a past race, in seconds."""
    df = race.laps
    if df is None or df.empty:
        return
    for driver in df["Driver"].unique():
        driver_laps = df[df["Driver"] == driver].sort_values("LapNumber")
        # Reference pace: median LapTime for green racing laps that aren't
        # pit-in, pit-out, or the opening lap.
        clean = driver_laps[
            driver_laps["PitInTime"].isna()
            & driver_laps["PitOutTime"].isna()
            & (driver_laps["TrackStatus"].astype(str) == "1")
            & driver_laps["LapTime"].notna()
            & (driver_laps["LapNumber"] > 1)
        ]
        if len(clean) < 5:
            continue
        ref = clean["LapTime"].dt.total_seconds().median()
        if not math.isfinite(ref):
            continue
        pit_ins = driver_laps[driver_laps["PitInTime"].notna()]
        for _, pit_lap in pit_ins.iterrows():
            lap_num = int(pit_lap["LapNumber"])
            out_lap = driver_laps[driver_laps["LapNumber"] == lap_num + 1]
            if out_lap.empty:
                continue
            out_lap = out_lap.iloc[0]
            if (
                str(pit_lap.get("TrackStatus", "1")) != "1"
                or str(out_lap.get("TrackStatus", "1")) != "1"
            ):
                continue
            in_time = pit_lap["LapTime"]
            out_time = out_lap["LapTime"]
            if pd.isna(in_time) or pd.isna(out_time):
                continue
            loss = (
                in_time.total_seconds() - ref
            ) + (out_time.total_seconds() - ref)
            if 10.0 < loss < 60.0:
                yield loss
