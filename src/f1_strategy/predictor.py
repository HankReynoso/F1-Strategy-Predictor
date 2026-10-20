"""Pre-race Prediction: race weekend description in, Strategy Prediction per driver out."""

import math
from dataclasses import dataclass
from itertools import product

from .degradation import DegradationEstimate, base_lap_time, team_degradation
from .settings import Settings
from .simulator import simulate, stop_windows
from .tyre_allocation import can_run, remaining_sets
from .weekend import DRY_COMPOUNDS, Compound, RaceWeekend


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

    predictions: dict[str, StrategyPrediction] = {}
    for driver, team in pre_race.teams.items():
        estimates = team_rates[team]
        rates = {c: e.rate for c, e in estimates.items()}
        predictions[driver] = _predict_driver(
            driver,
            estimates,
            rates,
            pre_race.race_laps,
            pre_race.pit_loss,
            base,
            driver_remaining[driver],
            settings,
        )
    return predictions


def _predict_driver(
    driver: str,
    estimates: dict[Compound, DegradationEstimate],
    rates: dict[Compound, float],
    race_laps: int,
    pit_loss: float,
    base: float,
    remaining: dict[Compound, int],
    settings: Settings,
) -> StrategyPrediction:
    simulated = []
    for strategy in legal_strategies():
        if not can_run(strategy.compounds, remaining):
            continue
        race = simulate(strategy.compounds, rates, race_laps, pit_loss, base)
        simulated.append((strategy, race))

    simulated.sort(key=lambda pair: pair[1].race_time)
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
                )
            ),
        )
        for (strategy, race), weight in zip(simulated, weights)
    )
    return StrategyPrediction(driver, candidates, estimates, dict(remaining))


def _require_dry_race(weekend: RaceWeekend) -> None:
    wet = sorted(
        {s.compound.name.title() for s in weekend.race.stints if not s.compound.is_dry}
    )
    if wet:
        raise NotDryRaceError(
            f"{weekend.pre_race.season} {weekend.pre_race.circuit} is not a Dry Race "
            f"(race laps on {', '.join(wet)}); Pre-race Predictions only cover Dry Races."
        )
