"""Degradation model: fuel-corrected Long Run fits, per team per Compound.

Each Long Run is a run of consecutive laps on one Tyre Set. We fit a per-lap
Degradation rate as the pooled within-Long-Run least-squares slope of lap time
against tyre age, grouped by team and Compound, then add the fuel effect
setting back on so the slope reflects pure tyre wear rather than the car
getting lighter.

A team with no Long Runs on a Compound uses the field average: the mean of
the fitted rates from teams that do have Long Runs on it. Every estimate
records whether it came from the team's own Long Runs or the field average.
"""

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from statistics import fmean

from .weekend import DRY_COMPOUNDS, Compound, Lap, PreRaceInfo


class DegradationSource(Enum):
    """Where a team's per-Compound Degradation estimate came from."""

    LONG_RUNS = "long_runs"
    FIELD_AVERAGE = "field_average"


@dataclass(frozen=True)
class DegradationEstimate:
    rate: float
    source: DegradationSource


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


def team_degradation(
    pre_race: PreRaceInfo, fuel_effect_s_per_lap: float
) -> dict[str, dict[Compound, DegradationEstimate]]:
    """Per-team per-Compound fuel-corrected Degradation, with a per-Compound
    field-average fallback for teams that have no Long Runs on a Compound.
    """
    by_team_compound: dict[tuple[str, Compound], list[list[Lap]]] = defaultdict(list)
    for run in long_runs(pre_race):
        team = pre_race.teams.get(run[0].driver)
        if team is None:
            continue
        by_team_compound[(team, run[0].compound)].append(run)

    team_rates: dict[tuple[str, Compound], float] = {}
    for key, runs in by_team_compound.items():
        rate = _fit_fuel_corrected_rate(runs, fuel_effect_s_per_lap)
        if rate is not None:
            team_rates[key] = rate

    field_average: dict[Compound, float] = {}
    for compound in DRY_COMPOUNDS:
        measured = [r for (_, c), r in team_rates.items() if c == compound]
        if measured:
            field_average[compound] = fmean(measured)

    teams = set(pre_race.teams.values())
    result: dict[str, dict[Compound, DegradationEstimate]] = {}
    for team in teams:
        per_compound: dict[Compound, DegradationEstimate] = {}
        for compound in DRY_COMPOUNDS:
            if (team, compound) in team_rates:
                per_compound[compound] = DegradationEstimate(
                    team_rates[(team, compound)], DegradationSource.LONG_RUNS
                )
            elif compound in field_average:
                per_compound[compound] = DegradationEstimate(
                    field_average[compound], DegradationSource.FIELD_AVERAGE
                )
            else:
                raise ValueError(
                    f"No Long Runs on {compound.name.title()} across the field; "
                    "cannot estimate Degradation."
                )
        result[team] = per_compound
    return result


def base_lap_time(pre_race: PreRaceInfo) -> float:
    """Fresh-tyre pace placeholder: the fastest Long Run lap in the field.

    It is the same for every Candidate Strategy of a driver, so it does not
    affect rankings; it only makes Simulated Race Time read as a race time.
    """
    return min(lap.lap_time for run in long_runs(pre_race) for lap in run)


def _fit_fuel_corrected_rate(
    runs: list[list[Lap]], fuel_effect_s_per_lap: float
) -> float | None:
    """Pooled within-run least-squares slope of lap time against tyre age,
    plus the fuel effect per lap. Clamped at zero: fuel correction makes
    negative fits rare, but noise in a short Long Run can still produce one.
    """
    sxy = sxx = 0.0
    for run in runs:
        mean_age = fmean(lap.tyre_age for lap in run)
        mean_time = fmean(lap.lap_time for lap in run)
        for lap in run:
            sxy += (lap.tyre_age - mean_age) * (lap.lap_time - mean_time)
            sxx += (lap.tyre_age - mean_age) ** 2
    if sxx <= 0:
        return None
    return max(0.0, sxy / sxx + fuel_effect_s_per_lap)
