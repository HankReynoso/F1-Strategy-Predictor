from itertools import pairwise

import pytest
from weekend_builder import TEAMS, standard_practice, weekend

from f1_strategy import (
    Compound,
    NeutralisationPeriod,
    NotDryRaceError,
    RaceOutcome,
    RaceWeekend,
    Stint,
    predict,
)

S, M, H = Compound.SOFT, Compound.MEDIUM, Compound.HARD


def candidate(prediction, *compounds):
    return next(c for c in prediction.candidates if c.strategy.compounds == compounds)


def test_every_driver_gets_a_strategy_prediction_summing_to_100_percent():
    predictions = predict(weekend(standard_practice(), TEAMS))

    assert set(predictions) == {"VER", "PER", "LEC"}
    for prediction in predictions.values():
        assert prediction.candidates
        assert sum(c.probability for c in prediction.candidates) == pytest.approx(1.0)


def test_candidate_strategies_are_every_legal_1_to_3_stop_strategy_and_never_single_compound():
    prediction = predict(weekend(standard_practice(), TEAMS))["VER"]
    strategies = [c.strategy for c in prediction.candidates]

    # 3^2-3 two-stint + 3^3-3 three-stint + 3^4-3 four-stint sequences
    assert len(strategies) == 6 + 24 + 78
    assert len(set(strategies)) == len(strategies)
    for strategy in strategies:
        assert 1 <= strategy.stops <= 3
        assert all(c.is_dry for c in strategy.compounds)
        assert len(set(strategy.compounds)) >= 2


def test_each_planned_stop_reports_its_best_stop_lap():
    # Worked by hand. 12 laps; a Stint of L laps on a Compound losing d s/lap
    # costs d*L*(L-1)/2. M->H: stints 4+8 cost 0.1*12 + 0.05*56 = 4.0 (best).
    # H->M mirrors it: 8+4. S->H: stints 2+10 cost 0.25*2 + 0.05*90 = 5.0.
    prediction = predict(
        weekend(standard_practice(soft=0.5, medium=0.2, hard=0.1), TEAMS, race_laps=12)
    )["VER"]

    assert [s.best_lap for s in candidate(prediction, M, H).stops] == [4]
    assert [s.best_lap for s in candidate(prediction, H, M).stops] == [8]
    assert [s.best_lap for s in candidate(prediction, S, H).stops] == [2]
    gap = (
        candidate(prediction, S, H).simulated_race_time
        - candidate(prediction, M, H).simulated_race_time
    )
    assert gap == pytest.approx(1.0)


def test_candidates_are_ranked_and_probability_falls_as_simulated_race_time_rises():
    prediction = predict(
        weekend(standard_practice(soft=0.5, medium=0.2, hard=0.1), TEAMS, race_laps=12)
    )["VER"]
    candidates = prediction.candidates

    probabilities = [c.probability for c in candidates]
    assert probabilities == sorted(probabilities, reverse=True)
    for faster, slower in pairwise(candidates):
        assert faster.simulated_race_time <= slower.simulated_race_time
        if slower.simulated_race_time - faster.simulated_race_time > 1e-9:
            assert faster.probability > slower.probability
    # From the worked example: M->H is 1.0 s quicker than S->H.
    assert (
        candidate(prediction, M, H).probability
        > candidate(prediction, S, H).probability
    )


def test_higher_degradation_shifts_the_favourite_toward_more_stops():
    # Estimated by hand for 57 laps and 22 s Pit Loss: at this Degradation the
    # best 1-stop costs ~62 s against ~68 s for the best 2-stop; at triple the
    # Degradation the 1-stop costs ~142 s against ~115 s for the 2-stop.
    gentle = predict(
        weekend(standard_practice(soft=0.12, medium=0.07, hard=0.04), TEAMS)
    )["VER"]
    harsh = predict(
        weekend(standard_practice(soft=0.36, medium=0.21, hard=0.12), TEAMS)
    )["VER"]

    assert gentle.candidates[0].strategy.stops == 1
    assert harsh.candidates[0].strategy.stops == 2


def test_changing_the_races_actual_stints_never_changes_the_prediction():
    one_stop = [Stint("VER", M, 1, 20), Stint("VER", H, 21, 57)]
    two_stop = [
        Stint("VER", S, 1, 10),
        Stint("VER", H, 11, 35),
        Stint("VER", M, 36, 57),
    ]
    before = weekend(standard_practice(), TEAMS, race_stints=one_stop)
    after = RaceWeekend(
        pre_race=before.pre_race,
        race=RaceOutcome(
            stints=tuple(two_stop),
            neutralisations=(NeutralisationPeriod("SC", 30, 33),),
        ),
    )

    assert predict(before) == predict(after)


@pytest.mark.parametrize("wet_compound", [Compound.INTERMEDIATE, Compound.WET])
def test_a_weekend_with_intermediate_or_wet_race_laps_is_refused(wet_compound):
    stints = [Stint("VER", M, 1, 20), Stint("VER", wet_compound, 21, 57)]

    with pytest.raises(NotDryRaceError, match="not a Dry Race"):
        predict(weekend(standard_practice(), TEAMS, race_stints=stints))
