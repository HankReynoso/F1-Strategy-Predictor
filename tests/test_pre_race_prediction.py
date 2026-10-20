import math
from itertools import pairwise

import pytest
from weekend_builder import TEAMS, standard_practice, weekend

from f1_strategy import (
    Compound,
    NeutralisationPeriod,
    NotDryRaceError,
    RaceOutcome,
    RaceWeekend,
    Settings,
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
    # An unlimited Plausible margin shows every legal Strategy before pruning.
    prediction = predict(
        weekend(standard_practice(), TEAMS), Settings(plausible_margin_s=math.inf)
    )["VER"]
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


def test_candidate_strategies_beyond_the_plausible_margin_are_excluded():
    # Worked by hand. 12 laps, 22 s Pit Loss, S/M/H lose 0.5/0.2/0.1 s/lap.
    # Best Degradation cost per 1-stop: M/H 4.0, S/H 5.0, S/M 8.6 (either
    # order). A 2-stop pays another 22 s of Pit Loss and can save at most the
    # 4.0 s, so it is at least 18 s behind. A 10 s Plausible margin keeps
    # exactly the six 1-stops.
    prediction = predict(
        weekend(standard_practice(soft=0.5, medium=0.2, hard=0.1), TEAMS, race_laps=12),
        Settings(plausible_margin_s=10.0),
    )["VER"]

    assert {c.strategy.compounds for c in prediction.candidates} == {
        (M, H), (H, M), (S, H), (H, S), (S, M), (M, S)
    }
    assert sum(c.probability for c in prediction.candidates) == pytest.approx(1.0)


def test_each_planned_stop_reports_a_stop_window_within_the_stop_window_margin():
    # Worked by hand. 12 laps, M loses 0.2 s/lap and H 0.1 s/lap. For M->H
    # stopping on lap p costs 0.1*p*(p-1) + 0.05*(12-p)*(11-p):
    #   p=2: 4.7  p=3: 4.2  p=4: 4.0 (best)  p=5: 4.1  p=6: 4.5
    # With a 0.25 s Stop Window margin, laps 3 to 5 are within it.
    prediction = predict(
        weekend(standard_practice(soft=0.5, medium=0.2, hard=0.1), TEAMS, race_laps=12),
        Settings(stop_window_margin_s=0.25),
    )["VER"]

    (stop,) = candidate(prediction, M, H).stops
    assert (stop.first_lap, stop.best_lap, stop.last_lap) == (3, 4, 5)


def test_low_degradation_gives_a_wider_stop_window_than_high_degradation():
    # Worked by hand for M->H over 57 laps: stopping on lap p costs
    # dM*p*(p-1)/2 + dH*(57-p)*(56-p)/2, best at lap 21 either way.
    # At 0.07/0.04 s/lap, laps 17-25 are within 1 s of the best (laps 16
    # and 26 are 1.3 and 1.45 s off); at double the Degradation every gap
    # doubles, so only laps 18-23 stay within 1 s.
    settings = Settings(stop_window_margin_s=1.0)
    low = predict(
        weekend(standard_practice(soft=0.12, medium=0.07, hard=0.04), TEAMS), settings
    )["VER"]
    high = predict(
        weekend(standard_practice(soft=0.24, medium=0.14, hard=0.08), TEAMS), settings
    )["VER"]

    (low_stop,) = candidate(low, M, H).stops
    (high_stop,) = candidate(high, M, H).stops
    assert (low_stop.first_lap, low_stop.best_lap, low_stop.last_lap) == (17, 21, 25)
    assert (high_stop.first_lap, high_stop.best_lap, high_stop.last_lap) == (18, 21, 23)


def test_a_two_stop_stop_window_lets_the_other_stop_move_to_suit():
    # Worked by brute force over every pair of stop laps for H->M->H over 57
    # laps (H 0.04, M 0.07 s/lap): best stops are laps 22 and 35. Letting the
    # other stop move to suit, laps 17-27 and 30-40 are within 1 s of the
    # best. Holding the other stop fixed would give only 18-26 and 31-39.
    prediction = predict(
        weekend(standard_practice(), TEAMS), Settings(stop_window_margin_s=1.0)
    )["VER"]

    first, second = candidate(prediction, H, M, H).stops
    assert (first.first_lap, first.best_lap, first.last_lap) == (17, 22, 27)
    assert (second.first_lap, second.best_lap, second.last_lap) == (30, 35, 40)


def test_default_settings_prune_to_plausible_strategies_with_multi_lap_stop_windows():
    # With 57 laps and 22 s Pit Loss, the best 1-stop beats every 3-stop by
    # well over the default Plausible margin, so no 3-stop is shown.
    prediction = predict(weekend(standard_practice(), TEAMS))["VER"]

    assert prediction.candidates
    assert all(c.strategy.stops <= 2 for c in prediction.candidates)
    assert sum(c.probability for c in prediction.candidates) == pytest.approx(1.0)
    for c in prediction.candidates:
        for stop in c.stops:
            assert stop.first_lap < stop.best_lap < stop.last_lap


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
