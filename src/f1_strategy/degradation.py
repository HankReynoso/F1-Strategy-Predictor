"""Degradation model: per-Compound per-team rates with shrinkage.

Each team's fitted Degradation on a Compound is blended with the field
average, so that short, noisy fits don't sit at exactly 0 (ticket 13).

The best signal for a team is its own **Long Runs**: a pooled within-run
least-squares slope of lap time against tyre age, with the fuel effect
setting added back on so the slope reflects pure tyre wear. When the team
has no Long Runs on a Compound, we use its **Push Laps** on that Compound,
fitted the same way across the Push Laps grouped per Tyre Set. When
neither is available, we fall back to the **field average**, and if even
that is empty (no team ran the Compound this weekend) to the circuit's
**race-history** Degradation for that Compound (ticket 11, ADR-0003), and
finally to the next-softer Compound's field-level rate as an **upper
bound** (a harder Compound is assumed to wear no faster).

**Shrinkage.** Each team's raw fit is blended with the field average,
leaning on its own fit when it has a lot of running on the Compound and
on the field average when it has little. The blend weights the team's own
fit by its lap count and the field average by `degradation_shrinkage_laps`
equivalent laps. The field average is a lap-count-weighted mean of the
raw (unshrunk, unclamped) rates of the **other** teams on the Compound,
so a team is never pulled toward itself and one team's noisy near-zero
fit doesn't lower the field average used by other teams. The raw rates
are intentionally not clamped before averaging: a short noisy run that
would previously fit to exactly zero stayed at zero and dragged the field
average down for everyone; by keeping the raw value (even if slightly
negative) and blending, the near-zero team is self-corrected by the pull
toward the field without poisoning the field. The shrunk value is
clamped at zero so Simulated Race Time never sees a negative rate.

Each estimate records which source its own data came from (or
`FIELD_AVERAGE` when the team has no data on the Compound).
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
    # No team ran the Compound in practice: Degradation came from previous
    # seasons' race Stints at this circuit (ticket 11, ADR-0003).
    CIRCUIT_HISTORY = "circuit_history"
    # No practice and no history: upper-bound by the next-softer Compound's
    # field-average Degradation (ticket 11, ADR-0003).
    NEXT_SOFTER_BOUND = "next_softer_bound"


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
    """Per-team per-Compound fuel-corrected Degradation with shrinkage to the
    field average, falling back through circuit race history and finally to
    the next-softer Compound's field-level rate as an upper bound.
    """
    classified = classify(pre_race, settings)
    team_lr = _fit_by_team_compound(
        classified.long_runs, pre_race.teams, settings.fuel_effect_s_per_lap
    )
    team_pl = _fit_by_team_compound(
        classified.push_lap_groups, pre_race.teams, settings.fuel_effect_s_per_lap
    )

    # Best signal per (team, compound): Long Runs preferred, Push Laps otherwise.
    team_raw: dict[tuple[str, Compound], tuple[float, int, DegradationSource]] = {}
    for key, (rate, n) in team_pl.items():
        team_raw[key] = (rate, n, DegradationSource.PUSH_LAPS)
    for key, (rate, n) in team_lr.items():
        team_raw[key] = (rate, n, DegradationSource.LONG_RUNS)

    # Per-Compound field-level fallback: used by every team that has no own
    # data on the Compound. Weekend field average first, then circuit race
    # history, then the next-softer Compound's own fallback.
    field_fallback = _field_fallbacks(team_raw, pre_race.historical_degradation)

    k = settings.degradation_shrinkage_laps
    result: dict[str, dict[Compound, DegradationEstimate]] = {}
    for team in set(pre_race.teams.values()):
        per_compound: dict[Compound, DegradationEstimate] = {}
        for compound in DRY_COMPOUNDS:
            own = team_raw.get((team, compound))
            others = [
                (r, n)
                for (t, c), (r, n, _) in team_raw.items()
                if c == compound and t != team
            ]
            field_avg = _weighted_mean(others)
            if own is not None:
                raw, n, source = own
                blended = (
                    (n * raw + k * field_avg) / (n + k)
                    if field_avg is not None
                    else raw
                )
                per_compound[compound] = DegradationEstimate(max(0.0, blended), source)
                continue
            fallback = field_fallback.get(compound)
            if fallback is None:
                raise ValueError(
                    f"No Long Runs or Push Laps on {compound.name.title()} across "
                    "the field, no previous-seasons' race Stints at this circuit, "
                    f"and no softer Compound to bound {compound.name.title()} by; "
                    "cannot estimate Degradation."
                )
            rate, source = fallback
            per_compound[compound] = DegradationEstimate(max(0.0, rate), source)
        result[team] = per_compound
    return result


def _field_fallbacks(
    team_raw: dict[tuple[str, Compound], tuple[float, int, DegradationSource]],
    historical: dict[Compound, "object"],
) -> dict[Compound, tuple[float, DegradationSource]]:
    """Resolve a (rate, source) for every dry Compound that reaches the
    field-level fallback chain, in softer→harder order so a Compound's
    next-softer bound sees the already-resolved softer rate.

    - Weekend field average (any team ran it) → FIELD_AVERAGE
    - Previous seasons' race Stints at this circuit → CIRCUIT_HISTORY
    - Next-softer Compound's resolved rate → NEXT_SOFTER_BOUND
    """
    # DRY_COMPOUNDS is (SOFT, MEDIUM, HARD), i.e. already softer→harder.
    resolved: dict[Compound, tuple[float, DegradationSource]] = {}
    for compound in DRY_COMPOUNDS:
        all_on_compound = [
            (r, n) for (_, c), (r, n, _) in team_raw.items() if c == compound
        ]
        field_avg = _weighted_mean(all_on_compound)
        if field_avg is not None:
            resolved[compound] = (field_avg, DegradationSource.FIELD_AVERAGE)
            continue
        hist = historical.get(compound)
        if hist is not None:
            resolved[compound] = (hist.rate, DegradationSource.CIRCUIT_HISTORY)
            continue
        # Softer Compound's resolved rate acts as an upper bound (harder
        # Compounds are assumed to wear no faster). SOFT has no softer bound.
        softer_bound = _softer_bound(compound, resolved)
        if softer_bound is not None:
            resolved[compound] = (softer_bound, DegradationSource.NEXT_SOFTER_BOUND)
    return resolved


def _softer_bound(
    compound: Compound,
    resolved: dict[Compound, tuple[float, DegradationSource]],
) -> float | None:
    """The already-resolved rate of the Compound one step softer than
    `compound`, if any. SOFT has no softer bound; Medium's softer is Soft;
    Hard's softer is Medium.
    """
    idx = DRY_COMPOUNDS.index(compound)
    if idx == 0:
        return None
    softer = DRY_COMPOUNDS[idx - 1]
    entry = resolved.get(softer)
    return entry[0] if entry is not None else None


def base_lap_time(pre_race: PreRaceInfo, settings: Settings | None = None) -> float:
    """Fresh-tyre pace placeholder: the fastest Long Run lap in the field.

    It is the same for every Candidate Strategy of a driver, so it does not
    affect rankings; it only makes Simulated Race Time read as a race time.
    """
    return min(
        lap.lap_time for run in long_runs(pre_race, settings) for lap in run
    )


def _weighted_mean(samples: list[tuple[float, int]]) -> float | None:
    """Lap-count-weighted mean of (rate, lap_count); None if no samples."""
    if not samples:
        return None
    total_n = sum(n for _, n in samples)
    if total_n <= 0:
        return fmean(r for r, _ in samples)
    return sum(r * n for r, n in samples) / total_n


def _fit_by_team_compound(
    runs: list[list[Lap]],
    teams: dict[str, str],
    fuel_effect_s_per_lap: float,
) -> dict[tuple[str, Compound], tuple[float, int]]:
    """Pooled raw rates per (team, Compound), with the lap count behind each."""
    by_team_compound: dict[tuple[str, Compound], list[list[Lap]]] = defaultdict(list)
    for run in runs:
        team = teams.get(run[0].driver)
        if team is None:
            continue
        by_team_compound[(team, run[0].compound)].append(run)
    rates: dict[tuple[str, Compound], tuple[float, int]] = {}
    for key, grouped in by_team_compound.items():
        fit = _fit_fuel_corrected_rate(grouped, fuel_effect_s_per_lap)
        if fit is not None:
            rates[key] = fit
    return rates


def _fit_fuel_corrected_rate(
    runs: list[list[Lap]], fuel_effect_s_per_lap: float
) -> tuple[float, int] | None:
    """Pooled within-run least-squares slope of lap time against tyre age,
    plus the fuel effect per lap. Returns the raw rate (not clamped) and the
    total lap count behind the fit. Clamping is deferred to the shrinkage
    step so near-zero noisy fits don't drag the field average down.
    """
    sxy = sxx = 0.0
    n = 0
    for run in runs:
        mean_age = fmean(lap.tyre_age for lap in run)
        mean_time = fmean(lap.lap_time for lap in run)
        for lap in run:
            sxy += (lap.tyre_age - mean_age) * (lap.lap_time - mean_time)
            sxx += (lap.tyre_age - mean_age) ** 2
        n += len(run)
    if sxx <= 0:
        return None
    return sxy / sxx + fuel_effect_s_per_lap, n
