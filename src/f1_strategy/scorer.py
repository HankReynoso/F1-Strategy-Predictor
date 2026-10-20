"""Scorer: compare Strategy Predictions with what drivers actually ran.

For each driver, the actual Strategy is extracted from their race Stints and
scored two ways. Strategy Match checks top-1 and top-3 on stop count and
Compound sequence only, so a stop a lap or two early still counts. Candidate
Strategies with the same probability form a tied group: the actual Strategy's
credit is the share of top-k slots the group covers divided by the group size,
so a 2-way tie for the top pick scores ½ top-1 and 1 top-3 (ticket 14). This
is independent of the order tied Candidate Strategies are enumerated in. Stop
Window hits are scored separately: the n-th actual stop lap is compared with
the n-th predicted Stop Window of the matching Candidate Strategy. A race with
any Safety Car or VSC period is flagged as a Neutralised Race. Scoreability is
read from `RaceOutcome.finishing_status`: a driver is scoreable only if they
took the chequered flag (lapped or not) and made at least one stop. Drivers
who retired — including those classified after retiring in the last few laps —
are unscoreable and left out of the race summary.
"""

from dataclasses import dataclass

from .predictor import CandidateStrategy, Strategy, StrategyPrediction
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
    top_1_credit: float
    top_3_credit: float
    stop_window_hits: tuple[bool, ...]
    unscoreable: bool


@dataclass(frozen=True)
class RaceSummary:
    scoreable_drivers: int
    top_1_credit: float
    top_3_credit: float
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
        top_1_credit=sum(s.top_1_credit for s in scoreable),
        top_3_credit=sum(s.top_3_credit for s in scoreable),
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
            top_1_credit=0.0,
            top_3_credit=0.0,
            stop_window_hits=(),
            unscoreable=True,
        )
    actual = ActualStrategy(
        compounds=tuple(stint.compound for stint in stints),
        stop_laps=tuple(stint.end_lap for stint in stints[:-1]),
    )
    candidates = prediction.candidates
    matched = next((c for c in candidates if c.strategy == actual.strategy), None)
    if matched is None:
        top_1_credit = 0.0
        top_3_credit = 0.0
        hits: tuple[bool, ...] = tuple(False for _ in actual.stop_laps)
    else:
        top_1_credit, top_3_credit = _tied_group_credit(candidates, matched)
        hits = tuple(
            window.first_lap <= stop_lap <= window.last_lap
            for stop_lap, window in zip(actual.stop_laps, matched.stops)
        )
    return DriverScore(
        driver=driver,
        actual=actual,
        top_1_credit=top_1_credit,
        top_3_credit=top_3_credit,
        stop_window_hits=hits,
        unscoreable=False,
    )


def _tied_group_credit(
    candidates: tuple[CandidateStrategy, ...], matched: CandidateStrategy
) -> tuple[float, float]:
    """Share of the top-1 and top-3 slots the matched candidate's tied group
    covers, divided by the group size.

    Ties are detected by exact probability equality. Mirrored Candidate
    Strategies have identical Simulated Race Times by construction (nothing in
    the simulator depends on Compound order), so their weights and normalised
    probabilities are byte-identical floats; exact equality is enough and
    needs no tolerance. Other coincidental float ties are rare and would
    score the same under any sensible tolerance.
    """
    # Rank by probability descending; stable, so tied candidates keep the
    # order predict() put them in (deterministic by construction, see
    # predictor._candidate_sort_key).
    ranked = sorted(
        enumerate(candidates), key=lambda pair: -pair[1].probability
    )
    tied_prob = matched.probability
    group_size = sum(1 for _, c in ranked if c.probability == tied_prob)
    group_first_rank = (
        next(rank for rank, (_, c) in enumerate(ranked, start=1)
             if c.probability == tied_prob)
    )
    group_last_rank = group_first_rank + group_size - 1
    top_1_slots = _overlap(1, 1, group_first_rank, group_last_rank)
    top_3_slots = _overlap(1, TOP_K, group_first_rank, group_last_rank)
    return top_1_slots / group_size, top_3_slots / group_size


def _overlap(a_lo: int, a_hi: int, b_lo: int, b_hi: int) -> int:
    return max(0, min(a_hi, b_hi) - max(a_lo, b_lo) + 1)


def _group_by_driver(stints: tuple[Stint, ...]) -> dict[str, list[Stint]]:
    by_driver: dict[str, list[Stint]] = {}
    for stint in stints:
        by_driver.setdefault(stint.driver, []).append(stint)
    for driver_stints in by_driver.values():
        driver_stints.sort(key=lambda stint: stint.start_lap)
    return by_driver
