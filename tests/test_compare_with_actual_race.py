from weekend_builder import TEAMS, standard_practice, weekend

from f1_strategy import (
    Compound,
    NeutralisationPeriod,
    RaceOutcome,
    RaceWeekend,
    Stint,
    Strategy,
    compare,
    predict,
)

S, M, H = Compound.SOFT, Compound.MEDIUM, Compound.HARD


def with_race(base, *, stints=(), neutralisations=(), finishing_status=None):
    stints = tuple(stints)
    if finishing_status is None:
        last_by_driver: dict[str, int] = {}
        for stint in stints:
            last_by_driver[stint.driver] = max(
                last_by_driver.get(stint.driver, 0), stint.end_lap
            )
        finishing_status = {
            driver: last_lap >= base.pre_race.race_laps
            for driver, last_lap in last_by_driver.items()
        }
    return RaceWeekend(
        pre_race=base.pre_race,
        race=RaceOutcome(
            stints=stints,
            neutralisations=tuple(neutralisations),
            finishing_status=dict(finishing_status),
        ),
    )


def test_actual_strategy_is_extracted_from_the_drivers_race_stints():
    base = weekend(standard_practice(), TEAMS)
    stints = [Stint("VER", M, 1, 25), Stint("VER", H, 26, 57)]
    race = with_race(base, stints=stints)

    comparison = compare(predict(base), race)

    actual = comparison.scores["VER"].actual
    assert actual is not None
    assert actual.strategy == Strategy((M, H))
    assert actual.stop_laps == (25,)


def test_actual_strategy_matching_the_top_candidate_is_a_top_1_match():
    base = weekend(standard_practice(), TEAMS)
    predictions = predict(base)
    top_strategy = predictions["VER"].candidates[0].strategy
    stints = _stints_for("VER", top_strategy.compounds, race_laps=57, stop_laps=[25])
    race = with_race(base, stints=stints)

    score = compare(predictions, race).scores["VER"]

    assert score.top_1_match is True
    assert score.top_3_match is True


def test_actual_strategy_in_top_3_but_not_top_1_is_a_top_3_match_only():
    base = weekend(standard_practice(), TEAMS)
    predictions = predict(base)
    third_strategy = predictions["VER"].candidates[2].strategy
    stints = _stints_for(
        "VER",
        third_strategy.compounds,
        race_laps=57,
        stop_laps=_evenly_spaced(57, third_strategy.stops),
    )
    race = with_race(base, stints=stints)

    score = compare(predictions, race).scores["VER"]

    assert score.top_1_match is False
    assert score.top_3_match is True


def test_actual_strategy_absent_from_the_prediction_counts_as_no_match():
    # Default predictions over 57 laps keep no 3-stops: an actual S->M->S->H
    # Strategy is absent, so it is neither top-1 nor top-3.
    base = weekend(standard_practice(), TEAMS)
    predictions = predict(base)
    assert all(c.strategy != Strategy((S, M, S, H)) for c in predictions["VER"].candidates)
    stints = _stints_for("VER", (S, M, S, H), race_laps=57, stop_laps=[12, 25, 40])
    race = with_race(base, stints=stints)

    score = compare(predictions, race).scores["VER"]

    assert score.top_1_match is False
    assert score.top_3_match is False


def test_a_stop_two_laps_outside_the_window_still_counts_as_a_strategy_match():
    # 12 laps, M->H has best stop lap 4 and (with the default 1 s margin) a
    # window of laps 3-5. Lap 7 is two laps past the window.
    base = weekend(
        standard_practice(soft=0.5, medium=0.2, hard=0.1), TEAMS, race_laps=12
    )
    predictions = predict(base)
    stints = [Stint("VER", M, 1, 7), Stint("VER", H, 8, 12)]
    race = with_race(base, stints=stints)

    score = compare(predictions, race).scores["VER"]

    assert score.actual.strategy == Strategy((M, H))
    # Strategy Match holds on stop count and Compound sequence alone.
    assert score.top_1_match is True or score.top_3_match is True
    # Window hit scored separately: lap 7 is outside the window.
    (hit,) = score.stop_window_hits
    assert hit is False


def test_stop_window_hits_are_scored_per_stop_against_the_matching_candidates_windows():
    base = weekend(
        standard_practice(soft=0.5, medium=0.2, hard=0.1), TEAMS, race_laps=12
    )
    predictions = predict(base)
    candidates = predictions["VER"].candidates
    mh = next(c for c in candidates if c.strategy == Strategy((M, H)))
    (window,) = mh.stops
    inside_lap = window.best_lap
    outside_lap = window.last_lap + 2

    inside_stints = [Stint("VER", M, 1, inside_lap), Stint("VER", H, inside_lap + 1, 12)]
    outside_stints = [
        Stint("VER", M, 1, outside_lap),
        Stint("VER", H, outside_lap + 1, 12),
    ]

    inside_hit = compare(predictions, with_race(base, stints=inside_stints)).scores[
        "VER"
    ].stop_window_hits
    outside_hit = compare(predictions, with_race(base, stints=outside_stints)).scores[
        "VER"
    ].stop_window_hits

    assert inside_hit == (True,)
    assert outside_hit == (False,)


def test_each_actual_stop_is_scored_against_the_nth_predicted_stop_window():
    # Multi-stop Stop Windows can overlap (ticket 05 comment). Score the n-th
    # actual stop against the n-th predicted window, not against whichever
    # contains the lap.
    base = weekend(standard_practice(), TEAMS)
    predictions = predict(base)
    candidates = predictions["VER"].candidates
    two_stop = next(c for c in candidates if c.strategy.stops == 2)
    first, second = two_stop.stops
    # A pair where the second actual stop happens inside the first window:
    # same first-stop lap; second stop on the first window's best lap.
    stints = _stints_for(
        "VER",
        two_stop.strategy.compounds,
        race_laps=57,
        stop_laps=[first.best_lap, first.best_lap + 1],
    )
    race = with_race(base, stints=stints)

    score = compare(predictions, race).scores["VER"]

    hits = score.stop_window_hits
    assert hits[0] is True
    # The second stop lap is not inside the second window.
    assert not (second.first_lap <= first.best_lap + 1 <= second.last_lap)
    assert hits[1] is False


def test_a_race_with_a_safety_car_period_is_a_neutralised_race():
    base = weekend(standard_practice(), TEAMS)
    stints = [Stint("VER", M, 1, 25), Stint("VER", H, 26, 57)]
    race = with_race(
        base, stints=stints, neutralisations=[NeutralisationPeriod("SC", 10, 14)]
    )

    comparison = compare(predict(base), race)

    assert comparison.neutralised_race is True


def test_a_race_with_a_virtual_safety_car_period_is_a_neutralised_race():
    base = weekend(standard_practice(), TEAMS)
    race = with_race(
        base,
        stints=[Stint("VER", M, 1, 25), Stint("VER", H, 26, 57)],
        neutralisations=[NeutralisationPeriod("VSC", 42, 45)],
    )

    assert compare(predict(base), race).neutralised_race is True


def test_a_race_with_no_safety_car_or_vsc_is_not_a_neutralised_race():
    base = weekend(standard_practice(), TEAMS)
    race = with_race(
        base, stints=[Stint("VER", M, 1, 25), Stint("VER", H, 26, 57)]
    )

    assert compare(predict(base), race).neutralised_race is False


def test_retired_drivers_are_unscoreable():
    # VER's last Stint ends before race_laps -> retired -> unscoreable.
    base = weekend(standard_practice(), TEAMS)
    stints = [Stint("VER", M, 1, 20), Stint("VER", H, 21, 30)]
    race = with_race(base, stints=stints)

    score = compare(predict(base), race).scores["VER"]

    assert score.unscoreable is True
    assert score.actual is None
    assert score.top_1_match is False
    assert score.top_3_match is False
    assert score.stop_window_hits == ()


def test_a_lapped_finisher_with_at_least_one_stop_is_scoreable():
    # VER's last Stint ends at lap 56, one short of 57: lapped finisher, not
    # retired. With the chequered flag taken (finishing_status True) they
    # must be scored.
    base = weekend(standard_practice(), TEAMS)
    predictions = predict(base)
    top = predictions["VER"].candidates[0]
    first, second = top.strategy.compounds
    stints = [Stint("VER", first, 1, top.stops[0].best_lap), Stint("VER", second, top.stops[0].best_lap + 1, 56)]
    race = with_race(base, stints=stints, finishing_status={"VER": True})

    score = compare(predictions, race).scores["VER"]

    assert score.unscoreable is False
    assert score.actual is not None
    assert score.actual.strategy == top.strategy
    assert score.top_1_match is True


def test_a_classified_driver_who_retired_near_the_end_is_unscoreable():
    # Mirrors the Magnussen case (Singapore 2024, retired lap 57 of 62,
    # classified 19th). Last Stint ends on race_laps - 1 like a lapped
    # finisher, but finishing_status says they didn't take the flag.
    base = weekend(standard_practice(), TEAMS)
    stints = [Stint("VER", M, 1, 25), Stint("VER", H, 26, 56)]
    race = with_race(base, stints=stints, finishing_status={"VER": False})

    score = compare(predict(base), race).scores["VER"]

    assert score.unscoreable is True
    assert score.actual is None


def test_a_finisher_who_never_stopped_is_still_unscoreable():
    base = weekend(standard_practice(), TEAMS)
    # Single Stint over the whole race, finishing_status True: a no-stop
    # finish is not a legal Dry Race Strategy, so it stays unscoreable.
    stints = [Stint("VER", M, 1, 57)]
    race = with_race(base, stints=stints, finishing_status={"VER": True})

    score = compare(predict(base), race).scores["VER"]

    assert score.unscoreable is True
    assert score.actual is None


def test_finishing_status_lives_on_race_outcome_and_does_not_change_predictions():
    base = weekend(standard_practice(), TEAMS)
    pre_race = base.pre_race
    stints = [Stint("VER", M, 1, 25), Stint("VER", H, 26, 56)]

    finished_race = with_race(base, stints=stints, finishing_status={"VER": True})
    retired_race = with_race(base, stints=stints, finishing_status={"VER": False})

    # finishing_status is on RaceOutcome, not PreRaceInfo.
    assert "finishing_status" not in pre_race.__dataclass_fields__
    assert "finishing_status" in finished_race.race.__dataclass_fields__
    # Predictions are identical regardless of finishing_status.
    assert predict(finished_race) == predict(retired_race)
    # But scorer reaches different conclusions.
    assert compare(predict(finished_race), finished_race).scores["VER"].unscoreable is False
    assert compare(predict(retired_race), retired_race).scores["VER"].unscoreable is True


def test_drivers_who_never_completed_a_stop_are_unscoreable():
    base = weekend(standard_practice(), TEAMS)
    # Single Stint over the whole race -> never pitted -> unscoreable.
    stints = [Stint("VER", M, 1, 57)]
    race = with_race(base, stints=stints)

    score = compare(predict(base), race).scores["VER"]

    assert score.unscoreable is True
    assert score.actual is None


def test_race_summary_counts_matches_and_window_hits_over_scoreable_drivers():
    base = weekend(standard_practice(), TEAMS)
    predictions = predict(base)
    top = predictions["VER"].candidates[0].strategy
    stops_top = _evenly_spaced(57, top.stops)
    stints = [
        # VER: top-1 match, inside the predicted windows.
        *_stints_for("VER", top.compounds, 57, _best_laps(predictions["VER"], top)),
        # PER: never pitted (unscoreable).
        Stint("PER", M, 1, 57),
        # LEC: retired on lap 10 (unscoreable).
        Stint("LEC", S, 1, 10),
    ]
    race = with_race(base, stints=stints)

    summary = compare(predictions, race).summary

    assert summary.scoreable_drivers == 1
    assert summary.top_1_matches == 1
    assert summary.top_3_matches == 1
    assert summary.stop_window_hits == top.stops


def _stints_for(driver, compounds, race_laps, stop_laps):
    assert len(stop_laps) == len(compounds) - 1
    stints = []
    start = 1
    for compound, stop_lap in zip(compounds[:-1], stop_laps):
        stints.append(Stint(driver, compound, start, stop_lap))
        start = stop_lap + 1
    stints.append(Stint(driver, compounds[-1], start, race_laps))
    return stints


def _evenly_spaced(race_laps, stops):
    return [round(race_laps * (k + 1) / (stops + 1)) for k in range(stops)]


def _best_laps(prediction, strategy):
    candidate = next(c for c in prediction.candidates if c.strategy == strategy)
    return [s.best_lap for s in candidate.stops]
