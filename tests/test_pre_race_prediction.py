import math
from itertools import pairwise

import pytest
from weekend_builder import (
    TEAMS,
    degrading_run,
    long_run,
    push_lap_set,
    standard_practice,
    weekend,
)

from f1_strategy import (
    Compound,
    DegradationSource,
    HistoricalDegradation,
    Lap,
    NeutralisationPeriod,
    NotDryRaceError,
    PreRaceInfo,
    RaceOutcome,
    RaceWeekend,
    RemainingSetsRule,
    Session,
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
    # An unlimited Plausible margin and a generous Tyre Allocation show every
    # legal Strategy before pruning by either rule.
    big_allocation = {S: 20, M: 20, H: 20}
    prediction = predict(
        _allocation_weekend(standard_practice(), TEAMS, tyre_allocation=big_allocation),
        Settings(plausible_margin_s=math.inf),
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
    # Minimum Stint length is lowered to 1 so the 12-lap scenarios can place
    # a stop near the start; ticket 13's default of 5 is defended elsewhere.
    prediction = predict(
        weekend(standard_practice(soft=0.5, medium=0.2, hard=0.1), TEAMS, race_laps=12),
        Settings(min_stint_length=1),
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
        Settings(plausible_margin_s=10.0, min_stint_length=1),
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
        Settings(stop_window_margin_s=0.25, min_stint_length=1),
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
    )

    # PER did no practice, so has the full allocation (2H, 3M, 8S) and can
    # still run H-M-H; VER has used 1 new Hard and would lose this strategy.
    first, second = candidate(prediction["PER"], H, M, H).stops
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
        weekend(standard_practice(soft=0.5, medium=0.2, hard=0.1), TEAMS, race_laps=12),
        Settings(min_stint_length=1),
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


# --- Ticket 02: per-team Degradation with fuel correction ---------------------

TWO_TEAMS = {"VER": "Red Bull Racing", "LEC": "Ferrari"}


def test_two_teams_with_different_long_runs_get_different_favourite_strategies():
    # Red Bull: the standard_practice Degradation (gentle); default settings put
    # the 1-stop M->H as the favourite. Ferrari: three times the Degradation on
    # every Compound; the earlier test_higher_degradation_shifts_the_favourite
    # case already proved that pushes the favourite to a 2-stop.
    laps = [
        *degrading_run("VER", "VER-S1", S, 0.12),
        *degrading_run("VER", "VER-M1", M, 0.07, first_lap=20),
        *degrading_run("VER", "VER-H1", H, 0.04, first_lap=40),
        *degrading_run("LEC", "LEC-S1", S, 0.36),
        *degrading_run("LEC", "LEC-M1", M, 0.21, first_lap=20),
        *degrading_run("LEC", "LEC-H1", H, 0.12, first_lap=40),
    ]
    predictions = predict(weekend(laps, TWO_TEAMS))

    assert predictions["VER"].candidates[0].strategy.stops == 1
    assert predictions["LEC"].candidates[0].strategy.stops == 2


def test_a_teams_degradation_source_is_long_runs_when_it_has_long_runs_on_the_compound():
    prediction = predict(weekend(standard_practice(), TEAMS))["VER"]

    assert prediction.team_degradation[S].source == DegradationSource.LONG_RUNS
    assert prediction.team_degradation[M].source == DegradationSource.LONG_RUNS
    assert prediction.team_degradation[H].source == DegradationSource.LONG_RUNS


def test_a_team_with_no_long_run_on_a_compound_uses_the_field_average_from_other_teams():
    # Red Bull did no Softs this weekend; Ferrari did. Red Bull's Soft estimate
    # should come from Ferrari (the only team on that Compound), tagged as the
    # field average, and should match Ferrari's rate.
    laps = [
        *degrading_run("VER", "VER-M1", M, 0.07),
        *degrading_run("VER", "VER-H1", H, 0.04, first_lap=20),
        *degrading_run("LEC", "LEC-S1", S, 0.12),
        *degrading_run("LEC", "LEC-M1", M, 0.07, first_lap=20),
        *degrading_run("LEC", "LEC-H1", H, 0.04, first_lap=40),
    ]
    predictions = predict(weekend(laps, TWO_TEAMS))

    assert predictions["VER"].team_degradation[S].source == DegradationSource.FIELD_AVERAGE
    assert predictions["VER"].team_degradation[M].source == DegradationSource.LONG_RUNS
    assert predictions["VER"].team_degradation[H].source == DegradationSource.LONG_RUNS
    assert predictions["LEC"].team_degradation[S].source == DegradationSource.LONG_RUNS
    assert predictions["VER"].team_degradation[S].rate == pytest.approx(
        predictions["LEC"].team_degradation[S].rate
    )


def test_the_field_average_is_the_mean_of_fitted_rates_across_teams_on_that_compound():
    # Two teams have Softs with meaningfully different fits (0.10 and 0.30);
    # a third team (Mercedes/HAM) has no Softs and should get the mean, 0.20.
    teams = {
        "VER": "Red Bull Racing",
        "LEC": "Ferrari",
        "HAM": "Mercedes",
    }
    laps = [
        *degrading_run("VER", "VER-S1", S, 0.10),
        *degrading_run("VER", "VER-M1", M, 0.07, first_lap=20),
        *degrading_run("VER", "VER-H1", H, 0.04, first_lap=40),
        *degrading_run("LEC", "LEC-S1", S, 0.30),
        *degrading_run("LEC", "LEC-M1", M, 0.07, first_lap=20),
        *degrading_run("LEC", "LEC-H1", H, 0.04, first_lap=40),
        # Mercedes: no Softs. Mediums and Hards present so the fallback only
        # applies to Softs.
        *degrading_run("HAM", "HAM-M1", M, 0.07),
        *degrading_run("HAM", "HAM-H1", H, 0.04, first_lap=20),
    ]
    predictions = predict(weekend(laps, teams))

    ham_soft = predictions["HAM"].team_degradation[S]
    assert ham_soft.source == DegradationSource.FIELD_AVERAGE
    assert ham_soft.rate == pytest.approx(0.20)


def test_fuel_correction_lifts_fitted_degradation_by_the_fuel_effect_setting():
    # Flat raw lap times across tyre age mean no visible slope: without fuel
    # correction a 1-stop costs only Pit Loss. With a 0.1 s/lap fuel effect the
    # fitted Degradation is 0.1 everywhere, so a 1-stop M->H over 57 laps now
    # pays an extra 0.05 * (n*(n-1) + (57-n)*(56-n)) ~ 80 s on top.
    flat_laps = [
        *long_run("VER", "VER-S1", S, [90.0] * 10),
        *long_run("VER", "VER-M1", M, [90.0] * 10, first_lap=20),
        *long_run("VER", "VER-H1", H, [90.0] * 10, first_lap=40),
        *long_run("LEC", "LEC-S1", S, [90.0] * 10),
        *long_run("LEC", "LEC-M1", M, [90.0] * 10, first_lap=20),
        *long_run("LEC", "LEC-H1", H, [90.0] * 10, first_lap=40),
    ]
    teams = {"VER": "Red Bull Racing", "LEC": "Ferrari"}
    no_fuel = predict(
        weekend(flat_laps, teams), Settings(fuel_effect_s_per_lap=0.0)
    )["VER"]
    with_fuel = predict(
        weekend(flat_laps, teams), Settings(fuel_effect_s_per_lap=0.1)
    )["VER"]

    best_no_fuel = no_fuel.candidates[0]
    best_with_fuel = with_fuel.candidates[0]
    assert best_with_fuel.simulated_race_time - best_no_fuel.simulated_race_time > 50.0


def test_a_long_run_that_only_improves_from_fuel_burn_fits_to_zero_degradation():
    # Raw times fall by exactly the fuel effect per lap: pure fuel burn, no
    # tyre wear. With matching fuel correction the fitted Degradation is 0.
    # Observable through the main seam: Simulated Race Time equals base time
    # plus Pit Loss alone, because no Stint costs anything.
    fuel_effect = 0.05
    laps = [
        *long_run("VER", "VER-S1", S, [90.0 - fuel_effect * i for i in range(10)]),
        *long_run(
            "VER", "VER-M1", M, [90.0 - fuel_effect * i for i in range(10)],
            first_lap=20,
        ),
        *long_run(
            "VER", "VER-H1", H, [90.0 - fuel_effect * i for i in range(10)],
            first_lap=40,
        ),
    ]
    teams = {"VER": "Red Bull Racing"}
    prediction = predict(
        weekend(laps, teams, race_laps=57, pit_loss=22.0),
        Settings(fuel_effect_s_per_lap=fuel_effect),
    )["VER"]

    # The base lap time is min raw time = 90 - 9*0.05 = 89.55 s on lap 10.
    base = 90.0 - fuel_effect * 9
    best_one_stop = next(c for c in prediction.candidates if c.strategy.stops == 1)
    assert best_one_stop.simulated_race_time == pytest.approx(57 * base + 22.0)
    for compound, estimate in prediction.team_degradation.items():
        assert estimate.rate == pytest.approx(0.0), compound


# --- Ticket 03: Long Run and Push Lap recognition -----------------------------

NO_FUEL = Settings(fuel_effect_s_per_lap=0.0)
SOLO_TEAM = {"VER": "Red Bull Racing"}


def _flat_other_compounds(driver: str, prefix: str) -> list[Lap]:
    """Clean, zero-Degradation Long Runs on Mediums and Hards for one driver.

    With `fuel_effect_s_per_lap=0.0` these fit to 0 rate exactly, so Softs is
    the only Compound whose source and rate the test needs to reason about.
    """
    return [
        *long_run(driver, f"{prefix}-M1", M, [90.0] * 8, first_lap=20),
        *long_run(driver, f"{prefix}-H1", H, [90.0] * 8, first_lap=40),
    ]


def test_slow_fast_slow_pattern_on_a_tyre_set_is_never_treated_as_long_run():
    # Classic push-cool-push-cool pattern on Softs: no consistent run exists,
    # so the set must not count as a Long Run. VER's Soft source is Push Laps.
    laps = [
        *push_lap_set("VER", "VER-S1", S, [92.0, 89.0, 91.0, 89.2, 91.0]),
        *_flat_other_compounds("VER", "VER"),
    ]

    prediction = predict(weekend(laps, SOLO_TEAM), NO_FUEL)["VER"]

    assert prediction.team_degradation[S].source == DegradationSource.PUSH_LAPS


def test_team_with_push_laps_but_no_long_runs_uses_push_lap_fall_off():
    # Two Push Laps on one Tyre Set at ages 2 and 4, times 89.0 and 89.4.
    # Fall-off = (89.4 - 89.0) / (4 - 2) = 0.2 s/lap. Zero fuel effect so the
    # fitted rate equals the fall-off exactly.
    laps = [
        *push_lap_set("VER", "VER-S1", S, [92.0, 89.0, 91.0, 89.4, 91.0]),
        *_flat_other_compounds("VER", "VER"),
    ]

    prediction = predict(weekend(laps, SOLO_TEAM), NO_FUEL)["VER"]

    assert prediction.team_degradation[S].source == DegradationSource.PUSH_LAPS
    assert prediction.team_degradation[S].rate == pytest.approx(0.2)


def test_several_push_laps_on_one_tyre_set_are_grouped_so_fall_off_is_measurable():
    # Three Push Laps on the same Tyre Set at ages 2, 4 and 6: times 89.0,
    # 89.3 and 89.6. A single Push Lap can tell us nothing about fall-off;
    # grouping them per set recovers the 0.15 s/lap slope.
    laps = [
        *push_lap_set(
            "VER", "VER-S1", S, [92.0, 89.0, 91.0, 89.3, 91.0, 89.6, 91.0]
        ),
        *_flat_other_compounds("VER", "VER"),
    ]

    prediction = predict(weekend(laps, SOLO_TEAM), NO_FUEL)["VER"]

    assert prediction.team_degradation[S].source == DegradationSource.PUSH_LAPS
    assert prediction.team_degradation[S].rate == pytest.approx(0.15)


def test_team_with_neither_long_runs_nor_push_laps_uses_field_average():
    # LEC has Push Laps on Softs (rate 0.2); VER did no Softs at all. VER's
    # Soft Degradation falls back to the field average, which is LEC's rate.
    teams = {"VER": "Red Bull Racing", "LEC": "Ferrari"}
    laps = [
        *_flat_other_compounds("VER", "VER"),
        *push_lap_set("LEC", "LEC-S1", S, [92.0, 89.0, 91.0, 89.4, 91.0]),
        *_flat_other_compounds("LEC", "LEC"),
    ]

    predictions = predict(weekend(laps, teams), NO_FUEL)

    assert predictions["LEC"].team_degradation[S].source == DegradationSource.PUSH_LAPS
    assert predictions["VER"].team_degradation[S].source == DegradationSource.FIELD_AVERAGE
    assert predictions["VER"].team_degradation[S].rate == pytest.approx(
        predictions["LEC"].team_degradation[S].rate
    )


def test_an_abnormally_slow_lap_inside_a_long_run_does_not_distort_degradation():
    # A Long Run of 10 Soft laps whose slope is 0.1 s/lap, with lap 5 made
    # 5 s slow by traffic. The slow lap is dropped so the fit stays at 0.1.
    traffic = [90.0 + 0.1 * i for i in range(10)]
    traffic[4] += 5.0
    laps = [
        *long_run("VER", "VER-S1", S, traffic),
        *_flat_other_compounds("VER", "VER"),
    ]

    prediction = predict(weekend(laps, SOLO_TEAM), NO_FUEL)["VER"]

    assert prediction.team_degradation[S].source == DegradationSource.LONG_RUNS
    assert prediction.team_degradation[S].rate == pytest.approx(0.1, abs=1e-6)


def test_pit_in_and_pit_out_laps_do_not_distort_long_run_degradation():
    # A Long Run on Softs bookended by a pit-out lap at the start and a
    # pit-in lap at the end: both are the length of a pit-lane transit (20 s
    # slower than the real stint) and must be excluded from the fit.
    inner = [
        Lap(driver="VER", lap_number=2 + i, lap_time=90.0 + 0.1 * i, tyre_set="VER-S1",
            compound=S, tyre_age=2 + i, new_when_fitted=True)
        for i in range(8)
    ]
    s_laps = [
        Lap(driver="VER", lap_number=1, lap_time=110.0, tyre_set="VER-S1", compound=S,
            tyre_age=1, new_when_fitted=True, pit_out=True),
        *inner,
        Lap(driver="VER", lap_number=10, lap_time=112.0, tyre_set="VER-S1", compound=S,
            tyre_age=10, new_when_fitted=True, pit_in=True),
    ]
    laps = [*s_laps, *_flat_other_compounds("VER", "VER")]

    prediction = predict(weekend(laps, SOLO_TEAM), NO_FUEL)["VER"]

    assert prediction.team_degradation[S].source == DegradationSource.LONG_RUNS
    assert prediction.team_degradation[S].rate == pytest.approx(0.1, abs=1e-6)


def test_sprint_race_stints_count_as_long_runs_on_sprint_weekends():
    # VER has no FP running on Softs; the Sprint race on Softs is a single
    # 15-lap consecutive-lap Stint at 0.1 s/lap. It must be treated as a Long
    # Run even though it comes from a session named "S" (Sprint race).
    sprint_laps = long_run("VER", "VER-S-sprint", S, [90.0 + 0.1 * i for i in range(15)])
    fp_laps = _flat_other_compounds("VER", "VER")
    sprint_weekend = RaceWeekend(
        pre_race=PreRaceInfo(
            circuit="Test",
            season=2024,
            race_laps=57,
            is_sprint_weekend=True,
            sessions=(
                Session(name="FP1", laps=tuple(fp_laps)),
                Session(name="S", laps=tuple(sprint_laps)),
            ),
            teams=SOLO_TEAM,
            pit_loss=22.0,
        ),
        race=RaceOutcome(),
    )

    prediction = predict(sprint_weekend, NO_FUEL)["VER"]

    assert prediction.team_degradation[S].source == DegradationSource.LONG_RUNS
    assert prediction.team_degradation[S].rate == pytest.approx(0.1, abs=1e-6)


def test_minimum_long_run_length_is_a_setting_with_a_default():
    # A 3-lap Softs run on its own is not a Long Run under the default
    # min_long_run_length. Dropping the setting to 3 flips VER's Softs from
    # the field-average fallback to its own Long Run fit.
    teams = {"VER": "Red Bull Racing", "LEC": "Ferrari"}
    laps = [
        *long_run("VER", "VER-S1", S, [90.0, 90.1, 90.2]),
        *_flat_other_compounds("VER", "VER"),
        *degrading_run("LEC", "LEC-S1", S, 0.3, fuel_burn=0.0),
        *_flat_other_compounds("LEC", "LEC"),
    ]

    default = predict(weekend(laps, teams), NO_FUEL)
    short = predict(
        weekend(laps, teams),
        Settings(fuel_effect_s_per_lap=0.0, min_long_run_length=3),
    )

    assert default["VER"].team_degradation[S].source == DegradationSource.FIELD_AVERAGE
    assert short["VER"].team_degradation[S].source == DegradationSource.LONG_RUNS
    # Ticket 13: the 3-lap raw fit (0.1) is pulled toward LEC's ample 0.3 by
    # shrinkage, so VER's own-fit rate sits between the two but is no longer
    # exactly 0.1. The source still flips to LONG_RUNS, which is the setting's
    # observable effect.
    assert 0.1 < short["VER"].team_degradation[S].rate < 0.3


# --- Ticket 04: Remaining Sets ------------------------------------------------


def _allocation_weekend(laps, teams, tyre_allocation=None, race_laps=57):
    """Weekend with an explicit per-driver Tyre Allocation override."""
    return RaceWeekend(
        pre_race=PreRaceInfo(
            circuit="Test Circuit",
            season=2024,
            race_laps=race_laps,
            is_sprint_weekend=False,
            sessions=(Session(name="FP2", laps=tuple(laps)),),
            teams=teams,
            pit_loss=22.0,
            tyre_allocation=tyre_allocation,
        ),
        race=RaceOutcome(stints=(), neutralisations=()),
    )


def test_default_allocation_rules_out_only_strategies_that_overshoot_a_compound():
    # PER drives nothing in practice; with the default allocation (8S, 3M,
    # 2H), the only strategies excluded by Remaining Sets are those needing
    # more than the allocation of some compound — in practice, 4-stint
    # strategies calling for 3+ Hards.
    prediction = predict(
        weekend(standard_practice(), TEAMS), Settings(plausible_margin_s=math.inf)
    )["PER"]
    strategies = [c.strategy.compounds for c in prediction.candidates]

    for compounds in strategies:
        assert compounds.count(H) <= 2
        assert compounds.count(M) <= 3
        assert compounds.count(S) <= 8
    # 108 legal strategies minus 8 four-stint strategies needing 3 Hards
    # (X-H-H-H and its three rotations for X in {S, M}).
    assert len(strategies) == 100


def test_a_driver_short_of_a_compound_loses_strategies_needing_more_of_it():
    # Allocation of 2H, 3M, 8S. VER's three Long Runs each start on a new
    # set, so VER has used 1 S, 1 M, 1 H and now has 7S / 2M / 1H.
    # Strategies needing 2 Hards (H-H, H-X-H, X-H-H, 3-stop variants with
    # two or more Hards) must disappear for VER. PER did nothing in
    # practice and still has 2H, so those strategies remain for PER.
    predictions = predict(
        weekend(standard_practice(), TEAMS), Settings(plausible_margin_s=math.inf)
    )
    ver_sets = {c.strategy.compounds for c in predictions["VER"].candidates}
    per_sets = {c.strategy.compounds for c in predictions["PER"].candidates}

    needs_two_hards = {s for s in per_sets if s.count(H) >= 2}
    assert needs_two_hards, "sanity: PER keeps strategies needing 2+ Hards"
    assert needs_two_hards.isdisjoint(ver_sets)
    # Everything VER has, PER has too (PER's Remaining Sets dominate VER's).
    assert ver_sets < per_sets


def test_teammates_with_identical_degradation_can_get_different_predictions_from_tyre_usage():
    # VER and PER are both on Red Bull with the same team Degradation. Each
    # drives one Soft, Medium and Hard Long Run; identical practice usage,
    # identical predictions. Then PER runs a SECOND new Hard: PER has 0
    # Hards remaining, VER still has 1, and every strategy using a Hard
    # falls away for PER but not VER.
    #
    # The allocation is overridden to effectively unbounded Soft and Medium
    # so the only binding constraint is the Hard count: it keeps the test
    # focused on the one difference between the drivers.
    hard_only = {S: 100, M: 100, H: 2}
    base_laps = [
        *degrading_run("VER", "VER-S1", S, 0.12),
        *degrading_run("VER", "VER-M1", M, 0.07, first_lap=20),
        *degrading_run("VER", "VER-H1", H, 0.04, first_lap=40),
        *degrading_run("PER", "PER-S1", S, 0.12),
        *degrading_run("PER", "PER-M1", M, 0.07, first_lap=20),
        *degrading_run("PER", "PER-H1", H, 0.04, first_lap=40),
    ]
    matched = predict(
        _allocation_weekend(base_laps, TEAMS, tyre_allocation=hard_only),
        Settings(plausible_margin_s=math.inf),
    )
    assert (
        {c.strategy.compounds for c in matched["VER"].candidates}
        == {c.strategy.compounds for c in matched["PER"].candidates}
    )

    diverged = predict(
        _allocation_weekend(
            [*base_laps, *degrading_run("PER", "PER-H2", H, 0.04, first_lap=60)],
            TEAMS,
            tyre_allocation=hard_only,
        ),
        Settings(plausible_margin_s=math.inf),
    )
    ver_sets = {c.strategy.compounds for c in diverged["VER"].candidates}
    per_sets = {c.strategy.compounds for c in diverged["PER"].candidates}

    assert diverged["VER"].remaining_sets[H] == 1
    assert diverged["PER"].remaining_sets[H] == 0
    assert per_sets < ver_sets
    assert all(H not in strategy for strategy in per_sets)
    assert any(H in strategy for strategy in ver_sets)


def test_strategies_needing_more_of_a_compound_than_the_allocation_are_excluded_for_everyone():
    # Override the allocation to 1 Hard total. Even a driver who did nothing
    # in practice cannot run two Hards, so strategies needing 2+ Hards
    # disappear across the board.
    one_hard = {S: 8, M: 3, H: 1}
    predictions = predict(
        _allocation_weekend(standard_practice(), TEAMS, tyre_allocation=one_hard),
        Settings(plausible_margin_s=math.inf),
    )

    for name, prediction in predictions.items():
        for cand in prediction.candidates:
            assert cand.strategy.compounds.count(H) <= 1, name


def test_used_sets_do_not_restore_capacity_lost_to_new_set_usage():
    # Pruning counts new sets only. A stint fitted on a used set does not
    # subtract from the allocation, so a driver who ran a Long Run on a
    # used Hard still has their full 2 new Hards available for the race.
    used_hard_run = [
        Lap(
            driver="VER",
            lap_number=1 + i,
            lap_time=90.0 + 0.04 * i,
            tyre_set="VER-used-H1",
            compound=H,
            tyre_age=5 + i,  # fitted at age 5 (not fresh)
            new_when_fitted=False,
        )
        for i in range(8)
    ]
    laps = [
        *degrading_run("VER", "VER-S1", S, 0.12, first_lap=20),
        *degrading_run("VER", "VER-M1", M, 0.07, first_lap=40),
        *used_hard_run,
        # PER drives nothing.
    ]
    predictions = predict(
        weekend(laps, TEAMS), Settings(plausible_margin_s=math.inf)
    )

    # No new Hards consumed by VER; VER's remaining Hards still equals the
    # allocation. If it didn't, strategies needing 2 Hards would disappear.
    assert predictions["VER"].remaining_sets[H] == 2
    assert predictions["PER"].remaining_sets[H] == 2
    needs_two_hards = {
        c.strategy.compounds
        for c in predictions["VER"].candidates
        if c.strategy.compounds.count(H) == 2
    }
    assert needs_two_hards, "sanity: VER can still run strategies with 2 Hards"


def test_remaining_sets_are_reported_on_the_prediction():
    # VER's Long Runs on each compound (all new sets) consume 1 of each.
    predictions = predict(
        weekend(standard_practice(), TEAMS), Settings(plausible_margin_s=math.inf)
    )

    # By default the allocation is 8S / 3M / 2H.
    assert predictions["VER"].remaining_sets == {S: 7, M: 2, H: 1}
    assert predictions["PER"].remaining_sets == {S: 8, M: 3, H: 2}


# Keep the import linter from pruning Lap: used in the used-sets test.
from f1_strategy import Lap  # noqa: E402


# --- Ticket 13: shrinkage and minimum Stint length ---------------------------


def test_short_slightly_negative_fit_gets_positive_rate_pulled_toward_field_average():
    # Team A: a 4-lap Soft run whose raw slope (−0.05 s/lap, +0.03 fuel) sits
    # slightly below zero. Teams B and C each ran a solid 8-lap Soft at 0.1
    # s/lap raw. With `degradation_shrinkage_laps=4` and 4 own laps, the blend
    # is 50/50 toward the leave-one-out field average of 0.1, so A lands near
    # 0.05, clearly positive — not stuck at the old zero clamp.
    teams = {"A1": "Alpha", "B1": "Bravo", "C1": "Charlie"}
    # Alpha's Medium and Hard sit below its shrunk Soft, so Compound ordering
    # (ticket 62) leaves the Soft as shrinkage made it.
    short_negative = long_run("A1", "A-S1", S, [91.00, 90.95, 90.90, 90.85])
    laps = [
        *short_negative,
        *degrading_run("A1", "A-M1", M, 0.03, first_lap=20),
        *degrading_run("A1", "A-H1", H, 0.02, first_lap=40),
        *degrading_run("B1", "B-S1", S, 0.10),
        *degrading_run("B1", "B-M1", M, 0.07, first_lap=20),
        *degrading_run("B1", "B-H1", H, 0.04, first_lap=40),
        *degrading_run("C1", "C-S1", S, 0.10),
        *degrading_run("C1", "C-M1", M, 0.07, first_lap=20),
        *degrading_run("C1", "C-H1", H, 0.04, first_lap=40),
    ]

    predictions = predict(weekend(laps, teams))

    alpha_soft = predictions["A1"].team_degradation[S]
    assert alpha_soft.source == DegradationSource.LONG_RUNS
    assert alpha_soft.rate > 0.0
    # The field average seen by Alpha (leave-one-out) is 0.10; the shrunk
    # rate is a meaningful blend of the two, well above zero.
    assert alpha_soft.rate == pytest.approx(0.04, abs=0.01)


def test_a_team_with_plenty_of_running_keeps_a_rate_close_to_its_own_fit():
    # Team A: two solid 8-lap Soft Long Runs on different sets (16 laps total)
    # at 0.08 s/lap. Team B: an 8-lap Soft Long Run at 0.30. With 16 own laps
    # vs 4 equivalent-laps from the field average, A keeps ~80% of its own
    # fit; the pulled rate is close to 0.08, not halfway to 0.30.
    teams = {"A1": "Alpha", "B1": "Bravo"}
    laps = [
        *degrading_run("A1", "A-S1", S, 0.08),
        *degrading_run("A1", "A-S2", S, 0.08, first_lap=20),
        *degrading_run("A1", "A-M1", M, 0.07, first_lap=40),
        *degrading_run("A1", "A-H1", H, 0.04, first_lap=50),
        *degrading_run("B1", "B-S1", S, 0.30),
        *degrading_run("B1", "B-M1", M, 0.07, first_lap=20),
        *degrading_run("B1", "B-H1", H, 0.04, first_lap=40),
    ]

    predictions = predict(weekend(laps, teams))

    alpha_soft = predictions["A1"].team_degradation[S]
    assert alpha_soft.source == DegradationSource.LONG_RUNS
    # Exact blend: (16 * 0.08 + 4 * 0.30) / 20 = 0.124.
    assert alpha_soft.rate == pytest.approx(0.124, abs=1e-6)
    # Closer to 0.08 (own fit) than to 0.19 (midpoint between own and field).
    assert alpha_soft.rate < 0.19


def test_one_teams_noisy_near_zero_fit_does_not_lower_the_field_average_for_others():
    # Team A: a short 4-lap Soft fit that lands near zero (raw ~0 with the
    # fuel effect). Teams B and C: large, clean 16-lap Soft runs at 0.10.
    # The field average SEEN BY B is leave-one-out: lap-count-weighted mean
    # across the other teams on Soft, i.e. (4*~0 + 16*0.10)/(4+16) = 0.08.
    # So B's own shrunk rate stays close to its own 0.10 — A's zero does not
    # drag what B is pulled toward below the trusted teams' values.
    teams = {"A1": "Alpha", "B1": "Bravo", "C1": "Charlie"}
    # A: 4 laps whose observed slope is -0.03 and raw rate (+0.03 fuel) is 0.
    short_zero = long_run("A1", "A-S1", S, [91.00, 90.97, 90.94, 90.91])
    laps = [
        *short_zero,
        *degrading_run("A1", "A-M1", M, 0.07, first_lap=20),
        *degrading_run("A1", "A-H1", H, 0.04, first_lap=40),
        *degrading_run("B1", "B-S1", S, 0.10, laps=16),
        *degrading_run("B1", "B-M1", M, 0.07, first_lap=30),
        *degrading_run("B1", "B-H1", H, 0.04, first_lap=50),
        *degrading_run("C1", "C-S1", S, 0.10, laps=16),
        *degrading_run("C1", "C-M1", M, 0.07, first_lap=30),
        *degrading_run("C1", "C-H1", H, 0.04, first_lap=50),
    ]

    predictions = predict(weekend(laps, teams))

    bravo_soft = predictions["B1"].team_degradation[S]
    # B's leave-one-out field avg = (4*0 + 16*0.10)/20 = 0.08. With 16 own
    # laps the blend is (16*0.10 + 4*0.08)/20 = 0.096. Well above 0.05.
    assert bravo_soft.rate == pytest.approx(0.096, abs=1e-3)
    assert bravo_soft.rate > 0.08


def test_no_candidate_strategy_contains_a_stint_shorter_than_the_minimum():
    # With default `min_stint_length=5`, every Stint across every Candidate
    # Strategy of every driver must be at least 5 laps.
    predictions = predict(weekend(standard_practice(), TEAMS))

    for prediction in predictions.values():
        for candidate in prediction.candidates:
            # Reconstruct Stint lengths from the planned stops.
            boundaries = [0, *[s.best_lap for s in candidate.stops], 57]
            lengths = [b - a for a, b in zip(boundaries, boundaries[1:])]
            for length in lengths:
                assert length >= 5


def test_no_stop_window_starts_before_the_minimum_stint_length():
    # Same weekend as above; with default `min_stint_length=5`, no Stop Window
    # may begin before lap 5 (any earlier stop would leave Stint 1 too short),
    # and the final stop may not sit past lap `race_laps - 5`.
    predictions = predict(weekend(standard_practice(), TEAMS))

    for prediction in predictions.values():
        for candidate in prediction.candidates:
            stops = candidate.stops
            for k, stop in enumerate(stops):
                assert stop.first_lap >= 5 * (k + 1)
                tail_stints = len(candidate.strategy.compounds) - (k + 1)
                assert stop.last_lap <= 57 - 5 * tail_stints


def test_on_a_very_flat_degradation_weekend_stop_windows_do_not_cover_the_whole_race():
    # Before ticket 13, when one team's Long Run on a Compound got clamped to
    # exactly 0, 1-stop Stop Windows for drivers on that team covered nearly
    # the whole race (laps 1-61 at Singapore). The clamp is gone, so even a
    # team whose own fit is near zero inherits the field's non-zero rate
    # through shrinkage. On a weekend where every raw fit is near zero but
    # the fuel-effect-only raw rate is 0.03 s/lap, 1-stop Stop Windows should
    # be well short of the race distance (not within a few laps of the full
    # feasible range).
    teams = {"VER": "Red Bull Racing", "LEC": "Ferrari"}
    flat_laps = [
        *long_run("VER", "VER-S1", S, [90.0] * 8),
        *long_run("VER", "VER-M1", M, [90.0] * 8, first_lap=20),
        *long_run("VER", "VER-H1", H, [90.0] * 8, first_lap=40),
        *long_run("LEC", "LEC-S1", S, [90.0] * 8),
        *long_run("LEC", "LEC-M1", M, [90.0] * 8, first_lap=20),
        *long_run("LEC", "LEC-H1", H, [90.0] * 8, first_lap=40),
    ]
    predictions = predict(weekend(flat_laps, teams))

    for prediction in predictions.values():
        for candidate in prediction.candidates:
            if candidate.strategy.stops != 1:
                continue
            (stop,) = candidate.stops
            width = stop.last_lap - stop.first_lap + 1
            assert width <= 20, (
                f"Stop Window laps {stop.first_lap}-{stop.last_lap} "
                "spans too much of the race"
            )


# --- Ticket 12: no runnable Strategy fallback --------------------------------


def _starving_laps(driver: str) -> list[Lap]:
    """Fit new sets of every Soft (8) and Hard (2) and 2 Mediums.

    After this, `remaining_sets` is {S: 0, M: 1, H: 0}; no 2-stint Strategy
    uses two different Compounds without at least 2 of one of them (M-H and
    H-M need 1M+1H, which has H=0; the only legal 1-stop with M=1,H=0,S=0
    is nothing), and no 3+ stint Strategy survives either. This re-creates
    Alonso's situation at Baku 2024.
    """
    laps: list[Lap] = []
    lap_number = 1
    for i in range(8):
        laps.append(
            Lap(
                driver=driver, lap_number=lap_number, lap_time=92.0,
                tyre_set=f"{driver}-newS-{i}", compound=S, tyre_age=1,
                new_when_fitted=True,
            )
        )
        lap_number += 1
    for i in range(2):
        for j in range(5):
            laps.append(
                Lap(
                    driver=driver, lap_number=lap_number, lap_time=90.0 + 0.04 * j,
                    tyre_set=f"{driver}-newM-{i}", compound=M, tyre_age=j + 1,
                    new_when_fitted=True,
                )
            )
            lap_number += 1
    for i in range(2):
        for j in range(5):
            laps.append(
                Lap(
                    driver=driver, lap_number=lap_number, lap_time=90.0 + 0.01 * j,
                    tyre_set=f"{driver}-newH-{i}", compound=H, tyre_age=j + 1,
                    new_when_fitted=True,
                )
            )
            lap_number += 1
    return laps


def test_no_runnable_strategy_falls_back_to_used_set_count_and_is_flagged():
    # ALO has new-only Remaining Sets S=0, M=1, H=0 — no legal Strategy. He
    # ran a used Hard set in practice (saved from a previous session), so
    # the used-set fallback adds 1 Hard back and M-H / H-M become runnable.
    # The flag `USED_SET_FALLBACK` is reported on the prediction.
    laps = [
        *_starving_laps("ALO"),
        # One used-Hard stint fitted in practice.
        *[
            Lap(
                driver="ALO", lap_number=200 + j, lap_time=91.0 + 0.03 * j,
                tyre_set="ALO-usedH-1", compound=H, tyre_age=5 + j,
                new_when_fitted=False,
            )
            for j in range(6)
        ],
        # VER gives the field a Degradation signal.
        *degrading_run("VER", "VER-S1", S, 0.12, first_lap=1),
        *degrading_run("VER", "VER-M1", M, 0.07, first_lap=20),
        *degrading_run("VER", "VER-H1", H, 0.04, first_lap=40),
    ]
    teams = {"ALO": "Aston Martin", "VER": "Red Bull Racing"}
    predictions = predict(weekend(laps, teams))

    alo = predictions["ALO"]
    assert alo.remaining_sets_rule is RemainingSetsRule.USED_SET_FALLBACK
    assert alo.remaining_sets[H] >= 1
    assert alo.candidates, "fallback must yield at least one Candidate Strategy"
    for cand in alo.candidates:
        assert set(cand.strategy.compounds) & {M, H}
    # The teammate (not actually a teammate, but a different team) is
    # unaffected: new-only rule applies.
    assert predictions["VER"].remaining_sets_rule is RemainingSetsRule.NEW_ONLY


def test_teammate_of_fallback_driver_is_unaffected():
    # ALO is starved; STR drives nothing. STR must get a normal, non-flagged
    # prediction under the new-only rule.
    laps = [
        *_starving_laps("ALO"),
        *degrading_run("VER", "VER-S1", S, 0.12, first_lap=1),
        *degrading_run("VER", "VER-M1", M, 0.07, first_lap=20),
        *degrading_run("VER", "VER-H1", H, 0.04, first_lap=40),
    ]
    teams = {"ALO": "Aston Martin", "STR": "Aston Martin", "VER": "Red Bull Racing"}
    predictions = predict(weekend(laps, teams))

    str_prediction = predictions["STR"]
    assert str_prediction.remaining_sets_rule is RemainingSetsRule.NEW_ONLY
    assert str_prediction.remaining_sets == {S: 8, M: 3, H: 2}
    assert predictions["ALO"].remaining_sets_rule in {
        RemainingSetsRule.USED_SET_FALLBACK,
        RemainingSetsRule.UNFILTERED_FALLBACK,
    }


def test_fallback_falls_through_to_unfiltered_when_used_sets_dont_help():
    # ALO is starved AND ran no used sets. Used-set fallback produces the
    # same empty pool, so the predictor falls through to UNFILTERED_FALLBACK
    # and the driver gets every legal 1-3 stop Strategy.
    laps = [
        *_starving_laps("ALO"),
        *degrading_run("VER", "VER-S1", S, 0.12, first_lap=1),
        *degrading_run("VER", "VER-M1", M, 0.07, first_lap=20),
        *degrading_run("VER", "VER-H1", H, 0.04, first_lap=40),
    ]
    teams = {"ALO": "Aston Martin", "VER": "Red Bull Racing"}
    predictions = predict(weekend(laps, teams), Settings(plausible_margin_s=math.inf))

    alo = predictions["ALO"]
    assert alo.remaining_sets_rule is RemainingSetsRule.UNFILTERED_FALLBACK
    assert alo.candidates
    # Unfiltered: should contain M-H and H-M and more.
    compounds_sets = {c.strategy.compounds for c in alo.candidates}
    assert (M, H) in compounds_sets
    assert (H, M) in compounds_sets
    # The pre-race prediction completes for everyone; no crash.
    assert predictions["VER"].candidates


def test_drivers_with_runnable_strategies_keep_new_only_rule():
    # The ticket-04 standard practice case: no driver is starved; everyone
    # gets NEW_ONLY. (Existing tests cover the strategy content; this test
    # just pins the flag.)
    predictions = predict(weekend(standard_practice(), TEAMS))
    for prediction in predictions.values():
        assert prediction.remaining_sets_rule is RemainingSetsRule.NEW_ONLY


# ---------------------------------------------------------------------------
# Ticket 11: no Degradation estimate when nobody runs a Compound in practice.
# Falls back to previous seasons' race Stints at the circuit, then to the
# next-softer Compound's field-average Degradation as an upper bound.
# ---------------------------------------------------------------------------


def _soft_and_medium_only(driver: str, prefix: str) -> list[Lap]:
    """Long Runs on Softs and Mediums for one driver. No Hard running at all,
    so the Hard rate must come from a later fallback step."""
    return [
        *long_run(driver, f"{prefix}-S1", S, [90.0 + 0.1 * i for i in range(8)]),
        *long_run(
            driver, f"{prefix}-M1",
            M,
            [90.0 + 0.05 * i for i in range(8)],
            first_lap=20,
        ),
    ]


def test_history_sourced_rate_used_when_no_team_runs_the_compound():
    # No team runs the Hard in practice but the loader has historical Hard
    # Degradation from previous seasons at the circuit: every team's Hard
    # estimate equals the historical rate, with CIRCUIT_HISTORY as the source.
    teams = {"VER": "Red Bull Racing", "LEC": "Ferrari"}
    laps = [*_soft_and_medium_only("VER", "VER"), *_soft_and_medium_only("LEC", "LEC")]
    # Below the 0.05 Medium, so Compound ordering (ticket 62) leaves it alone.
    history = {
        H: HistoricalDegradation(rate=0.03, seasons=(2023,), stint_count=5),
    }

    predictions = predict(weekend(laps, teams, historical_degradation=history), NO_FUEL)

    for driver in teams:
        hard = predictions[driver].team_degradation[H]
        assert hard.source == DegradationSource.CIRCUIT_HISTORY
        assert hard.rate == pytest.approx(0.03, abs=1e-9)


def test_next_softer_bound_used_when_no_history():
    # Same unrun-Hard weekend, this time with no history. Hard falls to the
    # next-softer bound: the Medium field-average rate (0.05 + fuel; here
    # NO_FUEL, so just 0.05). Both teams see the same bound.
    teams = {"VER": "Red Bull Racing", "LEC": "Ferrari"}
    laps = [*_soft_and_medium_only("VER", "VER"), *_soft_and_medium_only("LEC", "LEC")]

    predictions = predict(weekend(laps, teams), NO_FUEL)

    for driver in teams:
        hard = predictions[driver].team_degradation[H]
        assert hard.source == DegradationSource.NEXT_SOFTER_BOUND
        # Medium rate: both teams at 0.05, no shrinkage pulls it off that; the
        # leave-one-out field average of 0.05 is what Hard reads here.
        assert hard.rate == pytest.approx(0.05, abs=1e-9)


def test_neither_fallback_is_used_when_any_team_runs_the_compound():
    # VER has a Hard Long Run; LEC has none. Even with historical Hard data
    # available, LEC's Hard source is FIELD_AVERAGE (from VER's rate), not
    # CIRCUIT_HISTORY: the fallback chain only kicks in when nobody ran it.
    teams = {"VER": "Red Bull Racing", "LEC": "Ferrari"}
    laps = [
        *_soft_and_medium_only("VER", "VER"),
        *long_run("VER", "VER-H1", H, [90.0 + 0.1 * i for i in range(8)], first_lap=40),
        *_soft_and_medium_only("LEC", "LEC"),
    ]
    history = {H: HistoricalDegradation(rate=99.0, seasons=(2023,), stint_count=5)}

    predictions = predict(weekend(laps, teams, historical_degradation=history), NO_FUEL)

    assert predictions["VER"].team_degradation[H].source == DegradationSource.LONG_RUNS
    assert predictions["LEC"].team_degradation[H].source == DegradationSource.FIELD_AVERAGE
    # 99.0 would be the history rate; the field-average read must not touch it.
    assert predictions["LEC"].team_degradation[H].rate < 1.0


def test_historical_degradation_never_uses_the_race_being_predicted():
    # The predictor reads `historical_degradation` and never the race's own
    # Stints. Build a weekend whose race.stints run Hards for 30 laps each —
    # a tempting leak — and confirm the prediction depends only on the
    # supplied history. Changing race.stints doesn't change the Hard rate.
    teams = {"VER": "Red Bull Racing"}
    laps = _soft_and_medium_only("VER", "VER")
    history = {H: HistoricalDegradation(rate=0.03, seasons=(2023,), stint_count=5)}
    leaky_race_stints = [
        Stint(driver="VER", compound=M, start_lap=1, end_lap=25),
        Stint(driver="VER", compound=H, start_lap=26, end_lap=57),
    ]

    with_race = predict(
        weekend(
            laps, teams,
            race_stints=leaky_race_stints,
            historical_degradation=history,
        ),
        NO_FUEL,
    )["VER"]
    without_race = predict(
        weekend(laps, teams, historical_degradation=history),
        NO_FUEL,
    )["VER"]

    assert with_race.team_degradation[H] == without_race.team_degradation[H]
    assert with_race.team_degradation[H].rate == pytest.approx(0.03, abs=1e-9)


def test_refuses_cleanly_when_no_fallback_applies():
    # No team runs the Soft at all, no history for any Compound, and Soft is
    # already the softest Compound so there is no softer bound. The predictor
    # refuses with a message that names the Compound, not a traceback.
    teams = {"VER": "Red Bull Racing"}
    laps = [
        *long_run("VER", "VER-M1", M, [90.0 + 0.05 * i for i in range(8)], first_lap=20),
        *long_run("VER", "VER-H1", H, [90.0 + 0.04 * i for i in range(8)], first_lap=40),
    ]

    with pytest.raises(ValueError, match="Soft"):
        predict(weekend(laps, teams), NO_FUEL)


def test_history_is_fuel_corrected_the_same_way_as_practice():
    # If the loader fuel-corrects history the same way practice is corrected,
    # the resulting rate reads as "pure wear per lap" — the same meaning as a
    # Long Run rate on the simulator. This test checks the predictor doesn't
    # add any extra fuel adjustment to the history rate: a HistoricalDegradation
    # rate flows into team_degradation unchanged (fuel correction is the
    # loader's job).
    teams = {"VER": "Red Bull Racing"}
    laps = _soft_and_medium_only("VER", "VER")
    # Below the 0.08 Medium, so Compound ordering (ticket 62) leaves it alone.
    history = {H: HistoricalDegradation(rate=0.06, seasons=(2022, 2023), stint_count=7)}

    # Default fuel setting; the predictor must not change the rate.
    prediction = predict(
        weekend(laps, teams, historical_degradation=history),
    )["VER"]

    assert prediction.team_degradation[H].rate == pytest.approx(0.06, abs=1e-9)
    assert prediction.team_degradation[H].source == DegradationSource.CIRCUIT_HISTORY


# --- Ticket 62: Compound ordering per team ------------------------------------
# After shrinkage, each team's dry rates are put in order, Soft ≥ Medium ≥
# Hard (ADR-0003). An inverted pair or run shares its plain mean.

ONE_TEAM = {"VER": "Red Bull Racing"}


def _one_team_practice(soft: float, medium: float, hard: float) -> list[Lap]:
    # One team only, so there is no field average to shrink towards and each
    # rate is exactly its own fit.
    return standard_practice(soft=soft, medium=medium, hard=hard)


def test_an_inverted_medium_hard_pair_shares_its_mean():
    prediction = predict(weekend(_one_team_practice(0.12, 0.04, 0.08), ONE_TEAM))["VER"]

    rates = {c: prediction.team_degradation[c].rate for c in (S, M, H)}
    assert rates[S] == pytest.approx(0.12, abs=1e-9)
    assert rates[M] == pytest.approx(0.06, abs=1e-9)
    assert rates[H] == pytest.approx(0.06, abs=1e-9)


def test_ordering_keeps_each_compounds_degradation_source():
    # Soft is a Long Run, Medium a Push Lap fit below the Hard Long Run: the
    # pooled Medium and Hard keep their own sources.
    laps = [
        *degrading_run("VER", "VER-S1", S, 0.12),
        *push_lap_set("VER", "VER-M1", M, [92.0, 89.0, 92.0, 89.0, 92.0], first_lap=20),
        *degrading_run("VER", "VER-H1", H, 0.08, first_lap=40),
    ]
    prediction = predict(weekend(laps, ONE_TEAM))["VER"]

    degradation = prediction.team_degradation
    assert degradation[S].source == DegradationSource.LONG_RUNS
    assert degradation[M].source == DegradationSource.PUSH_LAPS
    assert degradation[H].source == DegradationSource.LONG_RUNS
    assert degradation[M].rate == pytest.approx(degradation[H].rate, abs=1e-9)
    assert degradation[M].rate < 0.08


def test_already_ordered_rates_are_untouched():
    prediction = predict(weekend(_one_team_practice(0.12, 0.07, 0.04), ONE_TEAM))["VER"]

    rates = {c: prediction.team_degradation[c].rate for c in (S, M, H)}
    assert rates == pytest.approx({S: 0.12, M: 0.07, H: 0.04}, abs=1e-9)


def test_an_inverted_run_of_three_compounds_shares_one_mean():
    # Soft below Medium pools to 0.03, which is still below the Hard, so all
    # three pool to (0.0 + 0.06 + 0.06) / 3 = 0.04.
    prediction = predict(weekend(_one_team_practice(0.0, 0.06, 0.06), ONE_TEAM))["VER"]

    for compound in (S, M, H):
        assert prediction.team_degradation[compound].rate == pytest.approx(0.04, abs=1e-9)


def test_ordering_pools_raw_rates_before_the_clamp_at_zero():
    # Soft fits to −0.04. Pooled unclamped: Soft and Medium share 0.01, below
    # the Hard's 0.02, so all three share 0.04 / 3. Clamping first would give
    # Soft and Medium 0.03 and leave the Hard at 0.02.
    prediction = predict(weekend(_one_team_practice(-0.04, 0.06, 0.02), ONE_TEAM))["VER"]

    for compound in (S, M, H):
        assert prediction.team_degradation[compound].rate == pytest.approx(
            0.04 / 3, abs=1e-9
        )


def test_ordering_also_covers_a_teams_field_level_fallback():
    # Red Bull ran no Hard; its Hard comes from Circuit History at 0.11, above
    # its own Medium Long Run (0.08 with the fuel effect), so they share 0.095.
    laps = _soft_and_medium_only("VER", "VER")
    history = {H: HistoricalDegradation(rate=0.11, seasons=(2023,), stint_count=5)}

    prediction = predict(weekend(laps, ONE_TEAM, historical_degradation=history))["VER"]

    assert prediction.team_degradation[M].rate == pytest.approx(0.095, abs=1e-9)
    assert prediction.team_degradation[H].rate == pytest.approx(0.095, abs=1e-9)
    assert prediction.team_degradation[H].source == DegradationSource.CIRCUIT_HISTORY


def test_a_pooled_soft_no_longer_makes_hard_to_soft_the_favourite():
    # A near-zero Soft fit (0.02) under a 0.08 Medium made the Soft look free,
    # so H → S was the top pick. Pooled, Soft and Medium share 0.05, above the
    # Hard's 0.04: H → S only ties H → M, which ranks first on the tie-break.
    prediction = predict(weekend(_one_team_practice(0.02, 0.08, 0.04), ONE_TEAM))["VER"]

    assert prediction.team_degradation[S].rate == pytest.approx(0.05, abs=1e-9)
    top = prediction.candidates[0].strategy.compounds
    assert top[-1] != S
    assert candidate(prediction, H, S).simulated_race_time == pytest.approx(
        candidate(prediction, H, M).simulated_race_time
    )
