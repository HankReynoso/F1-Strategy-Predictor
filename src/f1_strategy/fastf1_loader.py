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

from .backtest import RaceSpec
from .location_aliases import location_group
from .pit_lane_table import estimated_pit_loss, pit_lane_entry
from .regulation_era import PIT_LOSS_PRE_ERA_MIN_SEASON, era_start
from .weekend import (
    DRY_COMPOUNDS,
    Compound,
    HistoricalDegradation,
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
    pit_loss_min_season: int | None = None,
    history_min_season: int | None = None,
    fuel_effect_s_per_lap: float = 0.03,
    history_min_stint_length: int = 4,
) -> RaceWeekend:
    """Load a FastF1 race weekend into the race weekend description.

    `event` is anything FastF1 accepts (official name or location name).
    `cache_dir` is the FastF1 on-disk cache; repeat loads come from it.
    `pit_loss_min_season` is the earliest season to draw Pit Loss data from.
    ``None`` means apply ADR-0004's exception: use the race's own Regulation
    Era first, falling back to pre-era seasons (from
    ``PIT_LOSS_PRE_ERA_MIN_SEASON``) only when the circuit has no same-era
    race before the one being predicted. Pass an explicit integer only to
    pin a lower bound in a test.
    `history_min_season` is the earliest season to fit historical Degradation
    from (previous seasons' race Stints at this circuit, ticket 11). ``None``
    means use the first season of ``season``'s Regulation Era (ADR-0004), the
    one source of truth; pass an explicit integer only to override that for a
    test. It must match the fuel effect in `Settings` so historical rates are
    directly comparable with weekend Long Run rates.
    """
    if history_min_season is None:
        history_min_season = era_start(season)
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

    (
        pit_loss,
        pit_loss_seasons,
        estimated_pit_loss,
        historical_degradation,
    ) = _measure_pit_loss_and_history(
        circuit=circuit,
        race_season=season,
        pit_loss_min_season=pit_loss_min_season,
        history_min_season=history_min_season,
        cache_dir=cache_dir,
        fuel_effect_s_per_lap=fuel_effect_s_per_lap,
        history_min_stint_length=history_min_stint_length,
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
            pit_loss_seasons=pit_loss_seasons,
            estimated_pit_loss=estimated_pit_loss,
            historical_degradation=historical_degradation,
        ),
        race=RaceOutcome(
            stints=stints,
            neutralisations=neutralisations,
            finishing_status=finishing_status,
        ),
    )


def list_season(
    season: int, cache_dir: str | Path = ".cache/fastf1"
) -> list[RaceSpec]:
    """Every race weekend in a season, in round order, with sprints marked.

    Pre-season testing weekends have `EventFormat == "testing"` and are
    excluded. A sprint weekend is anything whose format is not
    `"conventional"`.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_dir))
    schedule = fastf1.get_event_schedule(season, include_testing=False)
    specs: list[RaceSpec] = []
    for _, row in schedule.sort_values("RoundNumber").iterrows():
        event_format = str(row.get("EventFormat", "conventional"))
        if event_format == "testing":
            continue
        specs.append(
            RaceSpec(
                season=season,
                event=str(row["EventName"]),
                is_sprint_weekend=event_format != "conventional",
            )
        )
    return specs


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


def _measure_pit_loss_and_history(
    circuit: str,
    race_season: int,
    pit_loss_min_season: int | None,
    history_min_season: int,
    cache_dir: str | Path,
    fuel_effect_s_per_lap: float,
    history_min_stint_length: int,
) -> tuple[float, tuple[int, ...], bool, dict[Compound, HistoricalDegradation]]:
    """Measure Pit Loss and Historical Degradation from past races.

    When ``pit_loss_min_season`` is ``None``, the ADR-0004 Pit Loss exception
    applies: try same-era seasons first, fall back to
    ``[PIT_LOSS_PRE_ERA_MIN_SEASON, history_min_season)`` when no same-era
    race at the circuit produced a Pit Loss sample, and finally estimate
    from the pit lane table (ticket 07) when the circuit has no earlier
    race under this FastF1 ``Location`` at all. When it is an explicit
    integer, that lower bound is honoured directly (used by tests that
    want to pin or widen the range); the pit-lane-table fallback is
    skipped in that case, so a pinned range that comes up empty still
    raises as before.

    Historical Degradation always draws from the same-era range
    ``[history_min_season, race_season)``; it has no pre-era or
    pit-lane-table fallback (ADR-0004's main rule).

    Returns ``(pit_loss, pit_loss_seasons, estimated_pit_loss,
    historical_degradation)``. ``pit_loss_seasons`` is empty when the
    estimate was used.
    """
    primary_min = (
        pit_loss_min_season if pit_loss_min_season is not None else history_min_season
    )
    pit_loss, pit_seasons, historical_degradation = _past_races_at_circuit(
        circuit=circuit,
        race_season=race_season,
        min_season=min(primary_min, history_min_season),
        cache_dir=cache_dir,
        fuel_effect_s_per_lap=fuel_effect_s_per_lap,
        history_min_stint_length=history_min_stint_length,
        pit_loss_min_season=primary_min,
        history_min_season=history_min_season,
        pit_loss_required=pit_loss_min_season is not None,
    )
    if pit_loss is not None:
        return pit_loss, pit_seasons, False, historical_degradation

    # Pit Loss fell through same-era: try pre-era seasons, keeping the
    # same-era Historical Degradation (ADR-0004 exception is Pit Loss only).
    pre_era_min = PIT_LOSS_PRE_ERA_MIN_SEASON
    pre_era_max = history_min_season  # exclusive upper bound
    if pre_era_min < pre_era_max:
        fallback_pit_loss, fallback_seasons, _ = _past_races_at_circuit(
            circuit=circuit,
            race_season=race_season,
            min_season=pre_era_min,
            cache_dir=cache_dir,
            fuel_effect_s_per_lap=fuel_effect_s_per_lap,
            history_min_stint_length=history_min_stint_length,
            pit_loss_min_season=pre_era_min,
            # Disable Historical Degradation inside this fallback call:
            # the real history was already measured against the same-era
            # range above.
            history_min_season=pre_era_max,
            pit_loss_required=False,
        )
        if fallback_pit_loss is not None:
            return (
                fallback_pit_loss,
                fallback_seasons,
                False,
                historical_degradation,
            )

    # Last fallback: estimate from the hand-maintained pit lane table
    # (ticket 07). This is only reached when FastF1 has no earlier race at
    # this ``Location`` to measure from — in 2022–2025 that is Miami 2022
    # and Las Vegas 2023.
    entry = pit_lane_entry(circuit)
    if entry is not None:
        return (
            estimated_pit_loss(entry),
            (),
            True,
            historical_degradation,
        )

    raise ValueError(
        f"no previous seasons' races at {circuit!r} were available to measure "
        f"Pit Loss from, and {circuit!r} has no entry in the pit lane table "
        f"(ticket 07)"
    )


def _past_races_at_circuit(
    circuit: str,
    race_season: int,
    min_season: int,
    cache_dir: str | Path,
    fuel_effect_s_per_lap: float,
    history_min_stint_length: int,
    pit_loss_min_season: int,
    history_min_season: int,
    pit_loss_required: bool = True,
) -> tuple[float | None, tuple[int, ...], dict[Compound, HistoricalDegradation]]:
    """Load each previous season's race at the circuit once and read both the
    Pit Loss sample and the historical Degradation sample from it.

    Pit Loss raises `ValueError` if no past data is available (unchanged
    behaviour). Historical Degradation is a best-effort dict: Compounds
    without a clean sample are simply absent, and `team_degradation` falls
    through to the next-softer bound.

    Both measures weight recent seasons more heavily by `0.5 ** (gap - 1)`,
    where `gap` is years between the past race and the race being predicted.
    The race being predicted is never read (season range stops at
    `race_season - 1`).
    """
    fastf1.Cache.enable_cache(str(cache_dir))
    # Cross-season Location aliases: FastF1 occasionally renames a venue
    # between seasons (e.g. Monte Carlo → Monaco in 2022, Miami → Miami
    # Gardens in 2025). The alias group lists every string that refers to
    # the same physical venue, so earlier seasons under the old name are
    # still matched (ticket 16).
    circuit_group = location_group(circuit)
    # (median_loss_for_race, weight, past season)
    pit_weighted: list[tuple[float, float, int]] = []
    # Per Compound: list of (per-stint rate, lap count, weight, past season)
    hist_samples: dict[Compound, list[tuple[float, int, float, int]]] = {
        c: [] for c in DRY_COMPOUNDS
    }
    for season in range(min_season, race_season):
        try:
            schedule = fastf1.get_event_schedule(season)
        except Exception:
            continue
        matches = schedule[schedule["Location"].isin(circuit_group)]
        for _, row in matches.iterrows():
            try:
                past = fastf1.get_session(season, int(row["RoundNumber"]), "R")
                past.load(laps=True, telemetry=False, weather=False, messages=False)
                if not hasattr(past, "_laps"):
                    # FastF1's `load` logs and continues when the live-timing
                    # API refuses the data (e.g. older seasons behind a 403).
                    continue
            except Exception:
                continue
            weight = 0.5 ** (race_season - season - 1)
            if season >= pit_loss_min_season:
                try:
                    losses = list(_pit_losses_in(past))
                except Exception:
                    losses = []
                if losses:
                    losses.sort()
                    pit_weighted.append((losses[len(losses) // 2], weight, season))
            if season >= history_min_season:
                for compound, rate, n in _historical_stint_rates(
                    past, fuel_effect_s_per_lap, history_min_stint_length
                ):
                    hist_samples[compound].append((rate, n, weight, season))

    if not pit_weighted:
        if pit_loss_required:
            raise ValueError(
                f"no previous seasons' races at {circuit!r} were available to measure "
                f"Pit Loss from (looked at {pit_loss_min_season}..{race_season - 1})"
            )
        pit_loss = None
        pit_loss_seasons: tuple[int, ...] = ()
    else:
        total_weight = sum(w for _, w, _ in pit_weighted)
        pit_loss = sum(m * w for m, w, _ in pit_weighted) / total_weight
        pit_loss_seasons = tuple(sorted({s for _, _, s in pit_weighted}))

    historical_degradation: dict[Compound, HistoricalDegradation] = {}
    for compound, samples in hist_samples.items():
        if not samples:
            continue
        # Lap-count × season-weight weighted mean of per-stint rates: a long,
        # recent Stint counts more than a short, old one. All rates are
        # already fuel-corrected per Stint, so the mean is directly a wear-
        # per-lap in the same units Long Run rates use.
        weights = [n * w for _, n, w, _ in samples]
        total = sum(weights)
        rate = sum(r * x for (r, _, _, _), x in zip(samples, weights)) / total
        seasons_used = tuple(sorted({s for _, _, _, s in samples}))
        historical_degradation[compound] = HistoricalDegradation(
            rate=rate,
            seasons=seasons_used,
            stint_count=len(samples),
        )
    return pit_loss, pit_loss_seasons, historical_degradation


def _historical_stint_rates(
    race, fuel_effect_s_per_lap: float, min_stint_length: int
) -> Iterable[tuple[Compound, float, int]]:
    """Per-Stint fuel-corrected Degradation rates from a past race, Compound-
    tagged. Yields `(compound, rate_s_per_lap, lap_count)` for every clean
    race Stint that has at least `min_stint_length` usable laps.

    Clean rule (recorded in ticket 11's implementation notes):
    - Drop pit-in and pit-out laps (first and last Stint lap are typically
      these; FastF1 flags both via `PitInTime` / `PitOutTime`).
    - Drop laps under SC or VSC (`TrackStatus` codes 4 / 6 / 7).
    - Drop laps whose `LapTime` is missing (safety-car bunches, red flags).
    - Drop laps that are not strictly consecutive after cleaning.
    - Drop the whole Stint if fewer than `min_stint_length` laps remain.

    Fuel correction is the same slope lift as practice (ticket 02): the
    within-run least-squares slope of lap time against tyre age, plus
    `fuel_effect_s_per_lap`. Over a full race Stint, tyre age and lap number
    advance 1:1 — exactly as inside a Long Run — so the correction has the
    same meaning as for a practice Long Run.
    """
    df = race.laps
    if df is None or df.empty:
        return
    for driver in df["Driver"].unique():
        driver_laps = df[df["Driver"] == driver].sort_values("LapNumber")
        if driver_laps.empty:
            continue
        for _, stint_laps in driver_laps.groupby("Stint", sort=True):
            compound_raw = stint_laps["Compound"].dropna()
            if compound_raw.empty:
                continue
            compound = _COMPOUND.get(str(compound_raw.iloc[0]).upper())
            if compound is None or compound not in DRY_COMPOUNDS:
                continue
            clean = []
            for _, lap in stint_laps.iterrows():
                if pd.isna(lap.get("LapTime")) or pd.isna(lap.get("TyreLife")):
                    continue
                if not pd.isna(lap.get("PitInTime")) or not pd.isna(
                    lap.get("PitOutTime")
                ):
                    continue
                if _lap_neutralisation_kind(str(lap.get("TrackStatus", "1"))) is not None:
                    continue
                clean.append(
                    (int(lap["TyreLife"]), float(lap["LapTime"].total_seconds()))
                )
            if len(clean) < min_stint_length:
                continue
            # Keep only the longest run of strictly consecutive tyre-age
            # values after dropping neutralised and pit laps mid-Stint.
            consecutive = _longest_consecutive(clean)
            if len(consecutive) < min_stint_length:
                continue
            rate = _slope(consecutive)
            if rate is None:
                continue
            yield compound, rate + fuel_effect_s_per_lap, len(consecutive)


def _longest_consecutive(points: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """Longest sub-sequence of `(tyre_age, lap_time)` whose tyre_age values
    increase by exactly 1 each step. Ties keep the first."""
    best: list[tuple[int, float]] = []
    current: list[tuple[int, float]] = []
    last_age: int | None = None
    for age, time in points:
        if last_age is not None and age == last_age + 1:
            current.append((age, time))
        else:
            current = [(age, time)]
        if len(current) > len(best):
            best = list(current)
        last_age = age
    return best


def _slope(points: list[tuple[int, float]]) -> float | None:
    """Least-squares slope of lap time against tyre age. None if the ages
    don't vary (defensive — the caller only passes consecutive runs ≥ 4)."""
    import statistics

    mean_x = statistics.fmean(x for x, _ in points)
    mean_y = statistics.fmean(y for _, y in points)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in points)
    sxx = sum((x - mean_x) ** 2 for x, _ in points)
    if sxx <= 0:
        return None
    return sxy / sxx


# Back-compat alias: tests from ticket 07 pin the old function name.
def _pit_loss_at_circuit(
    circuit: str,
    race_season: int,
    min_season: int,
    cache_dir: str | Path,
) -> float:
    pit_loss, _, _ = _past_races_at_circuit(
        circuit=circuit,
        race_season=race_season,
        min_season=min_season,
        cache_dir=cache_dir,
        fuel_effect_s_per_lap=0.03,
        history_min_stint_length=4,
        pit_loss_min_season=min_season,
        history_min_season=race_season,  # history disabled: no past seasons >=.
    )
    return pit_loss


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
