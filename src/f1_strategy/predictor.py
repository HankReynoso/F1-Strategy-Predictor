"""Pre-race Prediction: race weekend description in, Strategy Prediction per driver out."""

import math
from dataclasses import dataclass
from enum import Enum
from itertools import product

from .degradation import DegradationEstimate, base_lap_time, team_degradation
from .settings import Settings
from .simulator import simulate, stop_windows
from .tyre_allocation import can_run, remaining_sets, remaining_sets_including_used
from .weekend import DRY_COMPOUNDS, Compound, RaceWeekend


class RemainingSetsRule(Enum):
    """Which Remaining Sets rule produced a driver's prediction.

    Most drivers are predicted under NEW_ONLY (ADR-0002): Remaining Sets is
    the FIA allocation minus new sets fitted in pre-race sessions. For a
    driver whose new-only count leaves no runnable Strategy, the predictor
    falls back to USED_SET_FALLBACK (ADR-0002 amendment): used sets fitted
    pre-race are added to the pool, capped at the allocation. If that still
    leaves nothing, UNFILTERED_FALLBACK gives the driver every legal Strategy
    with no Remaining Sets pruning at all.
    """

    NEW_ONLY = "new-only"
    USED_SET_FALLBACK = "used-set fallback"
    UNFILTERED_FALLBACK = "unfiltered fallback"


class NotDryRaceError(ValueError):
    """Raised for a race weekend outside the model's scope (not a Dry Race)."""


@dataclass(frozen=True)
class Strategy:
    compounds: tuple[Compound, ...]

    @property
    def stops(self) -> int:
        return len(self.compounds) - 1


@dataclass(frozen=True)
class PlannedStop:
    """A planned pit stop: its Stop Window (first to last lap) and best stop lap."""

    first_lap: int
    best_lap: int
    last_lap: int


@dataclass(frozen=True)
class CandidateStrategy:
    strategy: Strategy
    probability: float
    simulated_race_time: float
    stops: tuple[PlannedStop, ...]


@dataclass(frozen=True)
class StrategyPrediction:
    driver: str
    candidates: tuple[CandidateStrategy, ...]
    team_degradation: dict[Compound, DegradationEstimate]
    remaining_sets: dict[Compound, int]
    remaining_sets_rule: RemainingSetsRule = RemainingSetsRule.NEW_ONLY


def legal_strategies() -> list[Strategy]:
    """Every 1-3 stop Strategy using at least two different dry Compounds."""
    return [
        Strategy(seq)
        for stints in range(2, 5)
        for seq in product(DRY_COMPOUNDS, repeat=stints)
        if len(set(seq)) >= 2
    ]


def predict(
    weekend: RaceWeekend, settings: Settings | None = None
) -> dict[str, StrategyPrediction]:
    settings = settings or Settings()
    _require_dry_race(weekend)
    # Everything below reads only pre-race information.
    pre_race = weekend.pre_race
    team_rates = team_degradation(pre_race, settings)
    base = base_lap_time(pre_race, settings)
    driver_remaining = remaining_sets(pre_race)
    fallback_remaining: dict[str, dict[Compound, int]] | None = None

    predictions: dict[str, StrategyPrediction] = {}
    for driver, team in pre_race.teams.items():
        estimates = team_rates[team]
        rates = {c: e.rate for c, e in estimates.items()}
        remaining = driver_remaining[driver]
        rule = RemainingSetsRule.NEW_ONLY
        if not _has_runnable_strategy(remaining, pre_race.race_laps, settings):
            if fallback_remaining is None:
                fallback_remaining = remaining_sets_including_used(pre_race)
            remaining = fallback_remaining[driver]
            rule = RemainingSetsRule.USED_SET_FALLBACK
            if not _has_runnable_strategy(remaining, pre_race.race_laps, settings):
                rule = RemainingSetsRule.UNFILTERED_FALLBACK
        predictions[driver] = _predict_driver(
            driver,
            estimates,
            rates,
            pre_race.race_laps,
            pre_race.pit_loss,
            base,
            remaining,
            rule,
            settings,
        )
    return predictions


def _has_runnable_strategy(
    remaining: dict[Compound, int], race_laps: int, settings: Settings
) -> bool:
    for strategy in legal_strategies():
        if len(strategy.compounds) * settings.min_stint_length > race_laps:
            continue
        if can_run(strategy.compounds, remaining):
            return True
    return False


def _predict_driver(
    driver: str,
    estimates: dict[Compound, DegradationEstimate],
    rates: dict[Compound, float],
    race_laps: int,
    pit_loss: float,
    base: float,
    remaining: dict[Compound, int],
    rule: RemainingSetsRule,
    settings: Settings,
) -> StrategyPrediction:
    simulated = []
    for strategy in legal_strategies():
        if rule is not RemainingSetsRule.UNFILTERED_FALLBACK and not can_run(
            strategy.compounds, remaining
        ):
            continue
        if len(strategy.compounds) * settings.min_stint_length > race_laps:
            continue
        race = simulate(
            strategy.compounds, rates, race_laps, pit_loss, base,
            settings.min_stint_length,
        )
        simulated.append((strategy, race))

    # Sort by simulated race time, with a deterministic tie-breaker on the
    # Compound sequence (ticket 14): two Candidate Strategies with the same
    # Simulated Race Time — mirrored Strategies like M → H and H → M always
    # tie by construction — otherwise land in whatever order
    # `legal_strategies()` produced them in, so re-ordering the enumeration
    # would silently re-rank tied candidates.
    simulated.sort(key=lambda pair: _candidate_sort_key(pair[0], pair[1].race_time))
    fastest = simulated[0][1].race_time
    # Only Plausible Candidate Strategies remain.
    simulated = [
        (strategy, race)
        for strategy, race in simulated
        if race.race_time - fastest <= settings.plausible_margin_s
    ]
    weights = [
        math.exp(-(race.race_time - fastest) / settings.probability_scale_s)
        for _, race in simulated
    ]
    total = sum(weights)
    candidates = tuple(
        CandidateStrategy(
            strategy=strategy,
            probability=weight / total,
            simulated_race_time=race.race_time,
            stops=tuple(
                PlannedStop(w.first_lap, w.best_lap, w.last_lap)
                for w in stop_windows(
                    strategy.compounds,
                    rates,
                    race_laps,
                    settings.stop_window_margin_s,
                    settings.min_stint_length,
                )
            ),
        )
        for (strategy, race), weight in zip(simulated, weights)
    )
    return StrategyPrediction(driver, candidates, estimates, dict(remaining), rule)


def _candidate_sort_key(
    strategy: Strategy, race_time: float
) -> tuple[float, tuple[str, ...]]:
    return race_time, tuple(c.value for c in strategy.compounds)


def _require_dry_race(weekend: RaceWeekend) -> None:
    wet = sorted(
        {s.compound.name.title() for s in weekend.race.stints if not s.compound.is_dry}
    )
    if wet:
        raise NotDryRaceError(
            f"{weekend.pre_race.season} {weekend.pre_race.circuit} is not a Dry Race "
            f"(race laps on {', '.join(wet)}); Pre-race Predictions only cover Dry Races."
        )
