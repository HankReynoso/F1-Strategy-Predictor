"""The end-to-end command and its printed report.

Hand-built weekends go through `predict` and `compare`, then the report
calls and the command, so no internet is needed. The command takes a
`load` function so tests can hand it a weekend instead of FastF1.
"""

import pytest
from weekend_builder import TEAMS, standard_practice, weekend

from f1_strategy import (
    Compound,
    NeutralisationPeriod,
    RaceOutcome,
    RaceWeekend,
    Stint,
    compare,
    predict,
)
from f1_strategy.cli import main
from f1_strategy.report import format_header, format_summary, format_table, strategy_label
from f1_strategy.settings import Settings

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


def two_stint(driver, first, second, stop_lap, race_laps=57):
    return [Stint(driver, first, 1, stop_lap), Stint(driver, second, stop_lap + 1, race_laps)]


def driver_block(table: str, driver: str) -> list[str]:
    """The table lines for one driver: their first line up to the next driver's."""
    lines = table.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(driver + " "))
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i][:1].strip()),
        len(lines),
    )
    return lines[start:end]


def test_strategy_label_reads_like_commentary():
    assert strategy_label((M, H)) == "1-stop: M → H"
    assert strategy_label((S, M, H)) == "2-stop: S → M → H"


def test_table_shows_each_drivers_top_3_candidates_with_probability_and_stop_windows():
    base = weekend(standard_practice(), TEAMS)
    predictions = predict(base)
    comparison = compare(predictions, base)

    table = format_table(predictions, comparison)

    for driver, prediction in predictions.items():
        block = driver_block(table, driver)
        assert len(block) == 3
        for row, candidate in zip(block, prediction.candidates):
            assert strategy_label(candidate.strategy.compounds) in row
            assert f"{candidate.probability:.0%}" in row
            for stop in candidate.stops:
                assert f"{stop.first_lap}–{stop.last_lap}" in row


def test_table_shows_the_actual_strategy_with_stop_laps_and_match_results():
    base = weekend(standard_practice(), TEAMS)
    predictions = predict(base)
    top = predictions["VER"].candidates[0]
    window = top.stops[0]
    first, second = top.strategy.compounds
    race = with_race(base, stints=two_stint("VER", first, second, window.best_lap))

    table = format_table(predictions, compare(predictions, race))

    ver_line = driver_block(table, "VER")[0]
    assert f"{strategy_label(top.strategy.compounds)} (lap {window.best_lap})" in ver_line
    # Default standard_practice makes M → H the top pick, tied with H → M:
    # ticket 14 splits the top-1 credit as 1/2 and keeps top-3 at 1.
    assert "top-1 1/2" in ver_line
    assert "top-3 1" in ver_line
    assert "Stop Window hits 1/1" in ver_line


def test_table_marks_a_miss_and_a_stop_outside_the_window():
    base = weekend(standard_practice(), TEAMS)
    predictions = predict(base)
    labels = [strategy_label(c.strategy.compounds) for c in predictions["LEC"].candidates]
    # S -> H, stopping on lap 2: not the favourite and far outside any window.
    assert labels[0] != strategy_label((S, H))
    race = with_race(base, stints=two_stint("LEC", S, H, 2))

    table = format_table(predictions, compare(predictions, race))

    lec_line = driver_block(table, "LEC")[0]
    assert "top-1 0" in lec_line
    assert "Stop Window hits 0/1" in lec_line


def test_table_marks_drivers_without_a_scoreable_race_as_unscoreable():
    base = weekend(standard_practice(), TEAMS)
    predictions = predict(base)
    # PER retires on lap 30 after one stop.
    race = with_race(base, stints=[Stint("PER", M, 1, 20), Stint("PER", H, 21, 30)])

    table = format_table(predictions, compare(predictions, race))

    per_line = driver_block(table, "PER")[0]
    assert "unscoreable" in per_line


def test_summary_reports_top_1_top_3_and_stop_window_hits_out_of_scoreable_drivers():
    base = weekend(standard_practice(), TEAMS)
    predictions = predict(base)
    top = predictions["VER"].candidates[0]
    first, second = top.strategy.compounds
    stints = [
        *two_stint("VER", first, second, top.stops[0].best_lap),
        *two_stint("LEC", S, H, 2),
    ]
    comparison = compare(predictions, with_race(base, stints=stints))

    summary = format_summary(comparison)

    assert "Scoreable drivers: 2 of 3" in summary
    # VER's top pick M → H is tied with H → M (ticket 14): 0.5 top-1 credit;
    # LEC's miss adds 0. Total 0.5 of 2 scoreable = 25%.
    assert "Top-1 Strategy Match: 0.5/2 (25%)" in summary
    assert "Stop Window hits: 1/2 actual stops (50%)" in summary
    assert "Neutralised Race: no" in summary


def test_summary_flags_a_neutralised_race():
    base = weekend(standard_practice(), TEAMS)
    predictions = predict(base)
    race = with_race(base, neutralisations=[NeutralisationPeriod("SC", 7, 9)])

    summary = format_summary(compare(predictions, race))

    assert "Neutralised Race: yes" in summary


def test_command_prints_the_table_then_the_summary_for_a_named_race(capsys):
    base = weekend(standard_practice(), TEAMS)
    top = predict(base)["VER"].candidates[0]
    race = with_race(
        base, stints=two_stint("VER", *top.strategy.compounds, top.stops[0].best_lap)
    )
    asked = []

    def load(season, event):
        asked.append((season, event))
        return race

    exit_code = main(["2024", "Test Grand Prix"], load=load)

    out = capsys.readouterr().out
    assert exit_code == 0
    assert asked == [(2024, "Test Grand Prix")]
    assert out.index("VER") < out.index("Top-1 Strategy Match")
    assert "Pit Loss 22.0 s" in out
    assert "probability_scale_s=5.0" in out


def test_command_refuses_a_race_that_is_not_dry(capsys):
    base = weekend(standard_practice(), TEAMS)
    wet = with_race(
        base,
        stints=[Stint("VER", Compound.INTERMEDIATE, 1, 20), Stint("VER", M, 21, 57)],
    )

    exit_code = main(["2024", "Test Grand Prix"], load=lambda season, event: wet)

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "is not a Dry Race" in captured.err
    assert "Intermediate" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_header_names_the_compound_that_leaned_on_circuit_history():
    # Ticket 11: when a Compound's rate came from circuit race history, the
    # header shows which Compound, the rate, the seasons and the Stint count.
    from weekend_builder import long_run
    from f1_strategy import HistoricalDegradation

    laps = [
        *long_run("VER", "VER-S1", S, [90.0 + 0.1 * i for i in range(8)]),
        *long_run("VER", "VER-M1", M, [90.0 + 0.05 * i for i in range(8)], first_lap=20),
    ]
    history = {H: HistoricalDegradation(rate=0.08, seasons=(2022, 2023), stint_count=7)}
    wkd = weekend(laps, {"VER": "Red Bull Racing"}, historical_degradation=history)
    predictions = predict(wkd, Settings(fuel_effect_s_per_lap=0.0))

    header = format_header(wkd.pre_race, Settings(), predictions)

    assert "Historical Degradation fallbacks:" in header
    assert "Hard: 0.080 s/lap (circuit history: seasons 2022, 2023, 7 Stints)" in header


def test_header_names_the_compound_that_fell_to_the_next_softer_bound():
    from weekend_builder import long_run

    laps = [
        *long_run("VER", "VER-S1", S, [90.0 + 0.1 * i for i in range(8)]),
        *long_run("VER", "VER-M1", M, [90.0 + 0.05 * i for i in range(8)], first_lap=20),
    ]
    wkd = weekend(laps, {"VER": "Red Bull Racing"})
    predictions = predict(wkd, Settings(fuel_effect_s_per_lap=0.0))

    header = format_header(wkd.pre_race, Settings(), predictions)

    assert "Historical Degradation fallbacks:" in header
    assert "Hard: 0.050 s/lap (next-softer bound from Medium)" in header


def test_header_omits_fallback_section_when_every_compound_was_run():
    predictions = predict(weekend(standard_practice(), TEAMS))
    header = format_header(weekend(standard_practice(), TEAMS).pre_race, Settings(), predictions)
    assert "Historical Degradation fallbacks:" not in header


def test_command_refuses_cleanly_when_no_fallback_can_estimate_a_compound(capsys):
    # Ticket 11: nobody ran Softs in practice, no history for any Compound,
    # and Soft is the softest — so no bound applies. The command must print
    # a clear refusal to stderr and exit 2, not raise a traceback.
    from weekend_builder import degrading_run

    laps = [
        *degrading_run("VER", "VER-M1", M, 0.07, first_lap=1),
        *degrading_run("VER", "VER-H1", H, 0.04, first_lap=20),
    ]
    wkd = weekend(laps, {"VER": "Red Bull Racing"})

    exit_code = main(["2024", "Test Grand Prix"], load=lambda season, event: wkd)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Soft" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_command_rejects_a_season_that_is_not_a_number(capsys):
    with pytest.raises(SystemExit):
        main(["twenty", "Test Grand Prix"], load=lambda season, event: None)
