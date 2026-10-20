"""Degradation model: per-Compound per-team rates with a three-step fallback.

Each team's Degradation on a Compound is fitted from fuel-corrected lap
times. The best signal is the team's own **Long Runs**: a pooled
within-run least-squares slope of lap time against tyre age, with the fuel
effect setting added back on so the slope reflects pure tyre wear. When
the team has no Long Runs on a Compound, we fall back to its **Push Laps**
on that Compound, fitted the same way across the Push Laps grouped per
Tyre Set. When neither is available, we fall back to the **field average**:
the mean of the best-available fitted rate across the other teams that do
have running on the Compound. Each estimate records which source it came
from.
"""

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from statistics import fmean

from .run_classifier import classify
from .settings import Settings
from .weekend import DRY_COMPOUNDS, Compound, Lap, PreRaceInfo


class DegradationSource(Enum):
    """Where a team's per-Compound Degradation estimate came from."""

    LONG_RUNS = "long_runs"
    PUSH_LAPS = "push_laps"
    FIELD_AVERAGE = "field_average"


@dataclass(frozen=True)
class DegradationEstimate:
    rate: float
    source: DegradationSource


def long_runs(pre_race: PreRaceInfo, settings: Settings | None = None) -> list[list[Lap]]:
    """Long Runs classified from this weekend's practice sessions."""
    return classify(pre_race, settings or Settings()).long_runs


def team_degradation(
    pre_race: PreRaceInfo, settings: Settings
) -> dict[str, dict[Compound, DegradationEstimate]]:
    """Per-team per-Compound fuel-corrected Degradation with a three-step
    fallback: team Long Runs, then team Push Laps, then the field average.
    """
    classified = classify(pre_race, settings)
    team_lr = _fit_by_team_compound(
        classified.long_runs, pre_race.teams, settings.fuel_effect_s_per_lap
    )
    team_pl = _fit_by_team_compound(
        classified.push_lap_groups, pre_race.teams, settings.fuel_effect_s_per_lap
    )

    # Best signal per (team, compound): Long Runs preferred, Push Laps otherwise.
    team_rate: dict[tuple[str, Compound], tuple[float, DegradationSource]] = {}
    for key, rate in team_pl.items():
        team_rate[key] = (rate, DegradationSource.PUSH_LAPS)
    for key, rate in team_lr.items():
        team_rate[key] = (rate, DegradationSource.LONG_RUNS)

    field_average: dict[Compound, float] = {}
    for compound in DRY_COMPOUNDS:
        measured = [r for (_, c), (r, _) in team_rate.items() if c == compound]
        if measured:
            field_average[compound] = fmean(measured)

    result: dict[str, dict[Compound, DegradationEstimate]] = {}
    for team in set(pre_race.teams.values()):
        per_compound: dict[Compound, DegradationEstimate] = {}
        for compound in DRY_COMPOUNDS:
            if (team, compound) in team_rate:
                rate, source = team_rate[(team, compound)]
                per_compound[compound] = DegradationEstimate(rate, source)
            elif compound in field_average:
                per_compound[compound] = DegradationEstimate(
                    field_average[compound], DegradationSource.FIELD_AVERAGE
                )
            else:
                raise ValueError(
                    f"No Long Runs or Push Laps on {compound.name.title()} across "
                    "the field; cannot estimate Degradation."
                )
        result[team] = per_compound
    return result


def base_lap_time(pre_race: PreRaceInfo, settings: Settings | None = None) -> float:
    """Fresh-tyre pace placeholder: the fastest Long Run lap in the field.

    It is the same for every Candidate Strategy of a driver, so it does not
    affect rankings; it only makes Simulated Race Time read as a race time.
    """
    return min(
        lap.lap_time for run in long_runs(pre_race, settings) for lap in run
    )


def _fit_by_team_compound(
    runs: list[list[Lap]],
    teams: dict[str, str],
    fuel_effect_s_per_lap: float,
) -> dict[tuple[str, Compound], float]:
    by_team_compound: dict[tuple[str, Compound], list[list[Lap]]] = defaultdict(list)
    for run in runs:
        team = teams.get(run[0].driver)
        if team is None:
            continue
        by_team_compound[(team, run[0].compound)].append(run)
    rates: dict[tuple[str, Compound], float] = {}
    for key, grouped in by_team_compound.items():
        rate = _fit_fuel_corrected_rate(grouped, fuel_effect_s_per_lap)
        if rate is not None:
            rates[key] = rate
    return rates


def _fit_fuel_corrected_rate(
    runs: list[list[Lap]], fuel_effect_s_per_lap: float
) -> float | None:
    """Pooled within-run least-squares slope of lap time against tyre age,
    plus the fuel effect per lap. Clamped at zero: fuel correction makes
    negative fits rare, but noise in a short run can still produce one.
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
