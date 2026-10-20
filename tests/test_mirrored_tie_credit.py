"""Ticket 14: tied Candidate Strategies get split credit.

If the actual Strategy ties with others for the top pick, it counts as a
fraction of a top-1 match. More generally, for a tied group of size k
covering ranks [r, r+k-1], the credit is (top-k slots the group covers) / k.
Scores no longer depend on the order Candidate Strategies were generated in.

Tests go through `predict()` and `compare()`. Hand-built predictions let us
force 4-way ties covering non-top ranks, which `predict()` alone does not
produce on the small weekend builder.
"""

from dataclasses import replace

import random

from weekend_builder import TEAMS, standard_practice, weekend

from f1_strategy import (
    CandidateStrategy,
    Compound,
    PlannedStop,
    RaceOutcome,
    RaceWeekend,
    Stint,
    Strategy,
    StrategyPrediction,
    compare,
    predict,
)

S, M, H = Compound.SOFT, Compound.MEDIUM, Compound.HARD


def _with_race(base, stints, finishing_status=None):
    stints = tuple(stints)
    if finishing_status is None:
        finishing_status = {
            s.driver: True for s in stints
        }
    return RaceWeekend(
        pre_race=base.pre_race,
        race=RaceOutcome(
            stints=stints,
            neutralisations=(),
            finishing_status=dict(finishing_status),
        ),
    )


def _candidate(strategy: Strategy, probability: float) -> CandidateStrategy:
    window = PlannedStop(1, 1, 1)
    stops = tuple(window for _ in range(strategy.stops))
    return CandidateStrategy(
        strategy=strategy,
        probability=probability,
        simulated_race_time=0.0,
        stops=stops,
    )


def _prediction(driver: str, candidates: tuple[CandidateStrategy, ...]) -> StrategyPrediction:
    return StrategyPrediction(
        driver=driver,
        candidates=candidates,
        team_degradation={},
        remaining_sets={},
    )


def test_actual_strategy_tied_2_ways_for_the_top_pick_scores_half_top_1_and_full_top_3():
    # VER's top pick on standard_practice is M → H, tied with H → M by
    # construction (nothing in the simulator depends on Compound order).
    base = weekend(standard_practice(), TEAMS)
    predictions = predict(base)
    top = predictions["VER"].candidates[0]
    assert any(
        c.strategy.compounds == tuple(reversed(top.strategy.compounds))
        and c.probability == top.probability
        for c in predictions["VER"].candidates[1:]
    ), "expected M → H / H → M to be tied for the top pick"

    stints = [Stint("VER", top.strategy.compounds[0], 1, 25),
              Stint("VER", top.strategy.compounds[1], 26, 57)]
    race = _with_race(base, stints)

    score = compare(predictions, race).scores["VER"]

    assert score.top_1_credit == 0.5
    assert score.top_3_credit == 1.0


def test_actual_strategy_in_a_4_way_tie_covering_ranks_2_to_5_scores_0_top_1_and_half_top_3():
    # Hand-built prediction: rank 1 untied, ranks 2–5 are a 4-way tied group.
    # Top-1 slots covered by the group = 0, top-3 slots = ranks 2 and 3 = 2,
    # so top-3 credit = 2 / 4 = 0.5.
    candidates = (
        _candidate(Strategy((M, H)), probability=0.40),
        _candidate(Strategy((H, M)), probability=0.15),
        _candidate(Strategy((S, H)), probability=0.15),
        _candidate(Strategy((H, S)), probability=0.15),
        _candidate(Strategy((S, M)), probability=0.15),
    )
    predictions = {"VER": _prediction("VER", candidates)}

    base = weekend(standard_practice(), TEAMS)
    # The actual Strategy is in the tied group at rank 3 of 5 (one of H → M,
    # S → H, H → S, S → M). Pick H → M.
    stints = [Stint("VER", H, 1, 25), Stint("VER", M, 26, 57)]
    race = _with_race(base, stints)

    score = compare(predictions, race).scores["VER"]

    assert score.top_1_credit == 0.0
    assert score.top_3_credit == 0.5


def test_untied_results_score_exactly_as_before():
    # Hand-built prediction with no ties: top-1 match = 1.0, miss = 0.0.
    candidates = (
        _candidate(Strategy((M, H)), probability=0.60),
        _candidate(Strategy((H, M)), probability=0.25),
        _candidate(Strategy((S, H)), probability=0.15),
    )
    predictions = {
        "VER": _prediction("VER", candidates),
        "PER": _prediction("PER", candidates),
    }
    base = weekend(standard_practice(), TEAMS)

    # VER runs the top pick: untied top-1 and top-3 = 1.0.
    ver_stints = [Stint("VER", M, 1, 25), Stint("VER", H, 26, 57)]
    # PER runs the third pick (untied): top-1 = 0, top-3 = 1.0.
    per_stints = [Stint("PER", S, 1, 25), Stint("PER", H, 26, 57)]
    race = _with_race(base, [*ver_stints, *per_stints])

    scores = compare(predictions, race).scores

    assert scores["VER"].top_1_credit == 1.0
    assert scores["VER"].top_3_credit == 1.0
    assert scores["PER"].top_1_credit == 0.0
    assert scores["PER"].top_3_credit == 1.0


def test_shuffling_candidate_strategies_in_a_hand_built_prediction_does_not_change_scores():
    # Group probabilities: rank 1 untied @ 0.30, ranks 2–3 tied @ 0.20,
    # ranks 4–5 tied @ 0.15.
    rng = random.Random(42)
    base_candidates = [
        _candidate(Strategy((M, H)), probability=0.30),
        _candidate(Strategy((H, M)), probability=0.20),
        _candidate(Strategy((S, H)), probability=0.20),
        _candidate(Strategy((H, S)), probability=0.15),
        _candidate(Strategy((S, M)), probability=0.15),
    ]

    base = weekend(standard_practice(), TEAMS)
    stints = [Stint("VER", H, 1, 25), Stint("VER", M, 26, 57)]
    race = _with_race(base, stints)

    scores = []
    for _ in range(5):
        shuffled = list(base_candidates)
        rng.shuffle(shuffled)
        predictions = {"VER": _prediction("VER", tuple(shuffled))}
        s = compare(predictions, race).scores["VER"]
        scores.append((s.top_1_credit, s.top_3_credit))

    # Every shuffle produces the same credits: H → M lives in the ranks-2–3
    # tied group, so top-1 credit = 0/2 = 0, top-3 credit = 2/2 = 1.
    assert all(score == scores[0] for score in scores)
    assert scores[0] == (0.0, 1.0)


def test_reordering_how_strategies_are_enumerated_does_not_change_any_predict_score():
    # predict() must put mirrored ties into a stated, deterministic order so
    # that enumerating Strategies differently never silently re-ranks them.
    base = weekend(standard_practice(), TEAMS)
    predictions = predict(base)

    # Shuffling the candidates for VER (same probabilities, different order)
    # must produce the same scores as the original.
    rng = random.Random(0)
    shuffled = list(predictions["VER"].candidates)
    rng.shuffle(shuffled)
    shuffled_predictions = dict(predictions)
    shuffled_predictions["VER"] = replace(
        predictions["VER"], candidates=tuple(shuffled)
    )

    stints = [Stint("VER", M, 1, 25), Stint("VER", H, 26, 57)]
    race = _with_race(base, stints)

    original = compare(predictions, race).scores["VER"]
    reordered = compare(shuffled_predictions, race).scores["VER"]

    assert original.top_1_credit == reordered.top_1_credit
    assert original.top_3_credit == reordered.top_3_credit


def test_summary_totals_are_sums_of_credits():
    # Two drivers both match a mirrored top tie: each contributes ½ top-1
    # and 1 top-3; summary totals are their sums.
    base = weekend(standard_practice(), TEAMS)
    predictions = predict(base)
    top = predictions["VER"].candidates[0]
    assert top.probability == predictions["VER"].candidates[1].probability

    stints = [
        Stint("VER", top.strategy.compounds[0], 1, 25),
        Stint("VER", top.strategy.compounds[1], 26, 57),
        Stint("PER", top.strategy.compounds[0], 1, 25),
        Stint("PER", top.strategy.compounds[1], 26, 57),
    ]
    race = _with_race(base, stints)

    summary = compare(predictions, race).summary

    assert summary.scoreable_drivers == 2
    assert summary.top_1_credit == 1.0
    assert summary.top_3_credit == 2.0
