"""Scorer: compare Strategy Predictions with what drivers actually ran.

For each driver, the actual Strategy is extracted from their race Stints and
scored two ways. Strategy Match checks top-1 and top-3 on stop count and
Compound sequence only, so a stop a lap or two early still counts. Stop Window
hits are scored separately: the n-th actual stop lap is compared with the n-th
predicted Stop Window of the matching Candidate Strategy. A race with any
Safety Car or VSC period is flagged as a Neutralised Race. Scoreability is
read from `RaceOutcome.finishing_status`: a driver is scoreable only if they
took the chequered flag (lapped or not) and made at least one stop. Drivers
who retired — including those classified after retiring in the last few laps —
are unscoreable and left out of the race summary.
"""

from dataclasses import dataclass

from .predictor import Strategy, StrategyPrediction
from .weekend import Compound, RaceWeekend, Stint


@dataclass(frozen=True)
class ActualStrategy:
    """What a driver actually ran: Compound sequence and the stop laps."""

    compounds: tuple[Compound, ...]
    stop_laps: tuple[int, ...]

    @property
    def strategy(self) -> Strategy:
        return Strategy(self.compounds)


@dataclass(frozen=True)
class DriverScore:
    driver: str
    actual: ActualStrategy | None
    top_1_match: bool
    top_3_match: bool
    stop_window_hits: tuple[bool, ...]
    unscoreable: bool


@dataclass(frozen=True)
class RaceSummary:
    scoreable_drivers: int
    top_1_matches: int
    top_3_matches: int
    stop_window_hits: int


@dataclass(frozen=True)
class RaceComparison:
    scores: dict[str, DriverScore]
    neutralised_race: bool
    summary: RaceSummary


TOP_K = 3


def compare(
    predictions: dict[str, StrategyPrediction], weekend: RaceWeekend
) -> RaceComparison:
    stints_by_driver = _group_by_driver(weekend.race.stints)
    finishing_status = weekend.race.finishing_status
    scores = {
        driver: _score_driver(
            driver,
            prediction,
            stints_by_driver.get(driver, []),
            finishing_status.get(driver, False),
        )
        for driver, prediction in predictions.items()
    }
    scoreable = [score for score in scores.values() if not score.unscoreable]
    summary = RaceSummary(
        scoreable_drivers=len(scoreable),
        top_1_matches=sum(s.top_1_match for s in scoreable),
        top_3_matches=sum(s.top_3_match for s in scoreable),
        stop_window_hits=sum(sum(s.stop_window_hits) for s in scoreable),
    )
    return RaceComparison(
        scores=scores,
        neutralised_race=bool(weekend.race.neutralisations),
        summary=summary,
    )


def _score_driver(
    driver: str,
    prediction: StrategyPrediction,
    stints: list[Stint],
    took_chequered_flag: bool,
) -> DriverScore:
    # Scoreable only if the driver took the chequered flag (lapped or not)
    # and made at least one stop. A Dry Race requires two Compounds, so a
    # finisher with a single Stint never ran a legal Strategy.
    unscoreable = not took_chequered_flag or len(stints) < 2
    if unscoreable:
        return DriverScore(
            driver=driver,
            actual=None,
            top_1_match=False,
            top_3_match=False,
            stop_window_hits=(),
            unscoreable=True,
        )
    actual = ActualStrategy(
        compounds=tuple(stint.compound for stint in stints),
        stop_laps=tuple(stint.end_lap for stint in stints[:-1]),
    )
    candidates = prediction.candidates
    top_1 = bool(candidates) and candidates[0].strategy == actual.strategy
    top_3 = any(c.strategy == actual.strategy for c in candidates[:TOP_K])
    matched = next((c for c in candidates if c.strategy == actual.strategy), None)
    if matched is None:
        hits = tuple(False for _ in actual.stop_laps)
    else:
        hits = tuple(
            window.first_lap <= stop_lap <= window.last_lap
            for stop_lap, window in zip(actual.stop_laps, matched.stops)
        )
    return DriverScore(
        driver=driver,
        actual=actual,
        top_1_match=top_1,
        top_3_match=top_3,
        stop_window_hits=hits,
        unscoreable=False,
    )


def _group_by_driver(stints: tuple[Stint, ...]) -> dict[str, list[Stint]]:
    by_driver: dict[str, list[Stint]] = {}
    for stint in stints:
        by_driver.setdefault(stint.driver, []).append(stint)
    for driver_stints in by_driver.values():
        driver_stints.sort(key=lambda stint: stint.start_lap)
    return by_driver
