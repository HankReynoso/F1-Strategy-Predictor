"""Degradation model (tracer-bullet version).

A Long Run is any run of consecutive laps on one Tyre Set. Degradation is one
field-wide rate per Compound: the pooled within-Long-Run least-squares slope of
lap time against tyre age. No fuel correction yet.
"""

from collections import defaultdict
from statistics import fmean

from .weekend import DRY_COMPOUNDS, Compound, Lap, PreRaceInfo


def long_runs(pre_race: PreRaceInfo) -> list[list[Lap]]:
    runs: list[list[Lap]] = []
    for session in pre_race.sessions:
        by_set: dict[tuple[str, str], list[Lap]] = defaultdict(list)
        for lap in session.laps:
            by_set[(lap.driver, lap.tyre_set)].append(lap)
        for laps in by_set.values():
            laps.sort(key=lambda lap: lap.lap_number)
            run = [laps[0]]
            for lap in laps[1:]:
                if lap.lap_number == run[-1].lap_number + 1:
                    run.append(lap)
                else:
                    runs.append(run)
                    run = [lap]
            runs.append(run)
    return [run for run in runs if len(run) >= 2]


def field_degradation(pre_race: PreRaceInfo) -> dict[Compound, float]:
    """Seconds lost per lap of tyre age, per dry Compound."""
    sxy: dict[Compound, float] = defaultdict(float)
    sxx: dict[Compound, float] = defaultdict(float)
    for run in long_runs(pre_race):
        mean_age = fmean(lap.tyre_age for lap in run)
        mean_time = fmean(lap.lap_time for lap in run)
        compound = run[0].compound
        for lap in run:
            sxy[compound] += (lap.tyre_age - mean_age) * (lap.lap_time - mean_time)
            sxx[compound] += (lap.tyre_age - mean_age) ** 2

    measured = {
        c: max(0.0, sxy[c] / sxx[c]) for c in DRY_COMPOUNDS if sxx.get(c, 0.0) > 0
    }
    if not measured:
        raise ValueError(
            "No Long Runs on any dry Compound; cannot estimate Degradation."
        )
    # A Compound with no Long Runs takes the average of the measured ones.
    fallback = fmean(measured.values())
    return {c: measured.get(c, fallback) for c in DRY_COMPOUNDS}


def base_lap_time(pre_race: PreRaceInfo) -> float:
    """Fresh-tyre pace placeholder: the fastest Long Run lap in the field.

    It is the same for every Candidate Strategy of a driver, so it does not
    affect rankings; it only makes Simulated Race Time read as a race time.
    """
    return min(lap.lap_time for run in long_runs(pre_race) for lap in run)
