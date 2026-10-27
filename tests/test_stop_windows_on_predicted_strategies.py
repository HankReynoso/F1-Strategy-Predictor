"""Ticket 58: Stop Window hits on Predicted-Strategy Stops, and window width.

The existing Stop Window hit figure counts hits over every actual stop, but
only a stop on a Strategy the model predicted (the actual Strategy is one of
the driver's Candidate Strategies) can ever be a hit. These tests go through
`run_backtest`, `save_backtest_result` / `load_backtest_result` and
`compare_backtest_results` with hand-built weekends.

Expected figures are read off `predict()` for the same weekend, so the tests
pin the counting rule rather than today's Stop Window laps.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from weekend_builder import TEAMS, standard_practice, weekend

from f1_strategy import (
    Compound,
    NeutralisationPeriod,
    RaceOutcome,
    RaceSpec,
    RaceWeekend,
    RunMetadata,
    Stint,
    load_backtest_result,
    predict,
    run_backtest,
    save_backtest_result,
)
from f1_strategy.backtest import format_backtest
from f1_strategy.backtest_compare import compare_backtest_results, format_comparison
from f1_strategy.settings import Settings

S, M, H = Compound.SOFT, Compound.MEDIUM, Compound.HARD
RACE_LAPS = 57
_REPO_RESULTS = Path(__file__).resolve().parent.parent / "results" / "backtest"


def _width(stop) -> int:
    """A Stop Window's width in laps, both ends counted ("lap 5–5" is 1)."""
    return stop.last_lap - stop.first_lap + 1


def _candidate(predictions, driver, *, stops: int):
    return next(
        c for c in predictions[driver].candidates if c.strategy.stops == stops
    )


def _stints(driver, compounds, stop_laps):
    bounds = [0, *stop_laps, RACE_LAPS]
    return [
        Stint(driver, compound, bounds[i] + 1, bounds[i + 1])
        for i, compound in enumerate(compounds)
    ]


def _race(
    *,
    season: int = 2024,
    circuit: str = "Alpha",
    is_sprint_weekend: bool = False,
    neutralised: bool = False,
    lec_on_candidate: bool = False,
):
    """A three-driver race with known Predicted-Strategy Stops.

    - VER runs his top Candidate Strategy and stops on its best lap: one
      Predicted-Strategy Stop, a hit.
    - PER runs a two-stop Candidate Strategy, stopping on the first lap of
      the first window (a hit) and one lap after the second window (a miss).
    - LEC runs S → M, which is not one of his Candidate Strategies: his stop
      counts towards the existing Stop Window hit figure only. With
      `lec_on_candidate`, he runs his top candidate and misses its window.

    Returns the weekend and the expected (hits, Predicted-Strategy Stops,
    Stop Window laps, all actual stops).
    """
    base = weekend(standard_practice(), TEAMS, race_laps=RACE_LAPS)
    base = replace(
        base,
        pre_race=replace(
            base.pre_race,
            season=season,
            circuit=circuit,
            is_sprint_weekend=is_sprint_weekend,
        ),
    )
    predictions = predict(base)
    ver = predictions["VER"].candidates[0]
    per = _candidate(predictions, "PER", stops=2)
    lec_actual = (S, M)
    assert all(
        c.strategy.compounds != lec_actual for c in predictions["LEC"].candidates
    ), "LEC's S → M must not be a Candidate Strategy for this test"

    ver_stop = ver.stops[0].best_lap
    per_stops = [per.stops[0].first_lap, per.stops[1].last_lap + 1]
    stints = [
        *_stints("VER", ver.strategy.compounds, [ver_stop]),
        *_stints("PER", per.strategy.compounds, per_stops),
    ]
    hits = 2
    predicted_stops = 3
    laps = _width(ver.stops[0]) + _width(per.stops[0]) + _width(per.stops[1])
    if lec_on_candidate:
        lec = predictions["LEC"].candidates[0]
        stints += _stints("LEC", lec.strategy.compounds, [lec.stops[0].last_lap + 1])
        predicted_stops += 1
        laps += _width(lec.stops[0])
    else:
        stints += _stints("LEC", lec_actual, [20])

    race = RaceOutcome(
        stints=tuple(stints),
        neutralisations=(
            (NeutralisationPeriod("SC", 10, 12),) if neutralised else ()
        ),
        finishing_status={"VER": True, "PER": True, "LEC": True},
    )
    return RaceWeekend(pre_race=base.pre_race, race=race), (
        hits,
        predicted_stops,
        laps,
        4,
    )


def _loader(mapping):
    def load(season, event):
        return mapping[(season, event)]

    return load


def _run(weekends: dict) -> object:
    specs = [RaceSpec(season, event) for season, event in weekends]
    return run_backtest(specs, load=_loader(weekends))


def _metadata(label="run") -> RunMetadata:
    return RunMetadata(
        label=label,
        run_at="2026-10-27T12:00:00+00:00",
        code_commit="abc123",
        uncommitted_changes=False,
        seasons_in_scope=(2024, 2025),
        settings=Settings(),
    )


def _saved(tmp_path: Path, result, label: str) -> Path:
    return save_backtest_result(result, tmp_path, metadata=_metadata(label)).data


def _rewrite_as_version_2(path: Path) -> None:
    """A file as ticket 39's build saved it: no per-race width keys."""
    data = json.loads(path.read_text())
    data["format_version"] = 2
    for race in data["races"]:
        del race["predicted_strategy_stops"]
        del race["stop_window_laps"]
    path.write_text(json.dumps(data))


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------


def test_each_race_records_its_predicted_strategy_stops_and_window_laps():
    wk, (hits, predicted_stops, laps, all_stops) = _race()

    race = _run({(2024, "Alpha GP"): wk}).races[0]

    assert race.predicted_strategy_stops == predicted_stops
    assert race.stop_window_laps == laps
    # The existing figure is unchanged: hits over every actual stop.
    assert race.summary.stop_window_hits == hits
    assert race.actual_stops == all_stops


def test_green_headline_reports_hits_over_predicted_strategy_stops_and_width():
    wk, (hits, predicted_stops, laps, all_stops) = _race()

    result = _run({(2024, "Alpha GP"): wk})
    headline = result.green_headline

    assert headline.stop_window_hits == hits
    assert headline.actual_stops == all_stops
    assert headline.predicted_strategy_stops == predicted_stops
    assert headline.stop_window_laps == laps


def test_neutralised_all_races_and_every_breakdown_carry_both_figures():
    green_2024, (_, g_stops, g_laps, _) = _race(circuit="Alpha")
    sprint_2024, (_, s_stops, s_laps, _) = _race(
        circuit="Beta", is_sprint_weekend=True, lec_on_candidate=True
    )
    neutral_2025, (_, n_stops, n_laps, _) = _race(
        season=2025, circuit="Gamma", neutralised=True
    )
    result = _run(
        {
            (2024, "Alpha GP"): green_2024,
            (2024, "Beta GP"): sprint_2024,
            (2025, "Gamma GP"): neutral_2025,
        }
    )

    def figures(totals):
        return (totals.predicted_strategy_stops, totals.stop_window_laps)

    assert figures(result.green_headline) == (g_stops + s_stops, g_laps + s_laps)
    assert figures(result.neutralised) == (n_stops, n_laps)
    assert figures(result.all_races) == (
        g_stops + s_stops + n_stops,
        g_laps + s_laps + n_laps,
    )
    assert figures(result.by_season[2024]) == (g_stops + s_stops, g_laps + s_laps)
    assert figures(result.by_season[2025]) == (n_stops, n_laps)
    assert figures(result.by_circuit["Beta"]) == (s_stops, s_laps)
    assert figures(result.by_sprint_weekend[True]) == (s_stops, s_laps)
    assert figures(result.by_sprint_weekend[False]) == (
        g_stops + n_stops,
        g_laps + n_laps,
    )
    assert figures(result.tuning) == (g_stops + s_stops, g_laps + s_laps)
    assert figures(result.held_out) == (n_stops, n_laps)


def test_race_averaged_figures_average_each_races_own_rate_and_width():
    alpha, (a_hits, a_stops, a_laps, _) = _race(circuit="Alpha")
    beta, (b_hits, b_stops, b_laps, _) = _race(circuit="Beta", lec_on_candidate=True)

    result = _run({(2024, "Alpha GP"): alpha, (2024, "Beta GP"): beta})
    averaged = result.green_headline_averaged

    assert averaged.races_with_predicted_strategy_stops == 2
    assert averaged.predicted_strategy_hit_rate_sum == pytest.approx(
        a_hits / a_stops + b_hits / b_stops
    )
    assert averaged.stop_window_width_sum == pytest.approx(
        a_laps / a_stops + b_laps / b_stops
    )
    assert result.all_races_averaged.races_with_predicted_strategy_stops == 2
    assert result.neutralised_averaged.races_with_predicted_strategy_stops == 0


def test_a_race_with_no_predicted_strategy_stops_has_zero_not_missing_figures():
    # Every driver on a Strategy that isn't a Candidate: the figures are
    # recorded as 0 stops, so the race doesn't count towards the average.
    wk, _ = _race()
    lec_only = RaceWeekend(
        pre_race=wk.pre_race,
        race=RaceOutcome(
            stints=tuple(_stints("LEC", (S, M), [20])),
            neutralisations=(),
            finishing_status={"LEC": True},
        ),
    )

    result = _run({(2024, "Alpha GP"): lec_only})

    assert result.races[0].predicted_strategy_stops == 0
    assert result.races[0].stop_window_laps == 0
    assert result.green_headline_averaged.races_with_predicted_strategy_stops == 0
    assert "Stop Window hits on predicted Strategies: 0/0 stops" in format_backtest(
        result
    )


def test_summary_shows_both_figures_with_numerator_and_denominator_everywhere():
    green, (hits, stops, laps, all_stops) = _race(circuit="Alpha")
    neutral, _ = _race(season=2025, circuit="Gamma", neutralised=True)
    result = _run({(2024, "Alpha GP"): green, (2025, "Gamma GP"): neutral})

    text = format_backtest(result)

    # Unchanged: the existing figure, over every actual stop.
    assert f"Stop Window hits: {hits}/{all_stops} actual stops" in text
    hit_line = (
        f"Stop Window hits on predicted Strategies: {hits}/{stops} stops "
        f"({hits / stops:.0%})"
    )
    width_line = (
        f"Average Stop Window width: {laps / stops:.1f} laps "
        f"({laps} laps over {stops} stops)"
    )
    green_section = text.split("Green-race headline (pooled over scoreable drivers):")[
        1
    ].split("\n\n")[0]
    assert hit_line in green_section
    assert width_line in green_section
    # Every block with the existing figure carries both new ones: green
    # pooled and race-averaged, Neutralised, all races, 2024, 2025, Alpha,
    # Gamma, conventional, Tuning Seasons, Held-out Season.
    blocks = [line for line in text.splitlines() if "Stop Window hits:" in line]
    assert len(blocks) == 11
    assert text.count("Stop Window hits on predicted Strategies:") == 11
    assert text.count("Average Stop Window width:") == 11
    averaged = text.split("Green-race headline (race-averaged):")[1].split("\n\n")[0]
    assert (
        f"Stop Window hits on predicted Strategies: mean {hits / stops:.0%} "
        "over 1 race(s)"
    ) in averaged
    assert f"Average Stop Window width: mean {laps / stops:.1f} laps over 1 race(s)" in (
        averaged
    )
    neutral_section = text.split("Neutralised Races only:")[1].split("\n\n")[0]
    assert "Stop Window hits on predicted Strategies:" in neutral_section
    assert "Average Stop Window width:" in neutral_section


# ---------------------------------------------------------------------------
# Saving and reading
# ---------------------------------------------------------------------------


def test_both_figures_are_saved_per_race_and_read_back_identical(tmp_path):
    alpha, _ = _race(circuit="Alpha")
    beta, _ = _race(season=2025, circuit="Beta", lec_on_candidate=True)
    result = _run({(2024, "Alpha GP"): alpha, (2025, "Beta GP"): beta})

    path = _saved(tmp_path, result, "v3")
    reloaded, metadata = load_backtest_result(path)
    saved = json.loads(path.read_text())

    assert saved["format_version"] == 3
    assert metadata.format_version == 3
    assert [
        (r["predicted_strategy_stops"], r["stop_window_laps"]) for r in saved["races"]
    ] == [(r.predicted_strategy_stops, r.stop_window_laps) for r in result.races]
    assert reloaded.races == result.races
    assert reloaded == result
    assert format_backtest(reloaded) == format_backtest(result)


def test_a_version_2_file_loads_with_both_figures_not_recorded(tmp_path):
    wk, _ = _race()
    path = _saved(tmp_path, _run({(2024, "Alpha GP"): wk}), "old")
    _rewrite_as_version_2(path)

    reloaded, metadata = load_backtest_result(path)

    assert metadata.format_version == 2
    assert reloaded.races[0].predicted_strategy_stops is None
    assert reloaded.races[0].stop_window_laps is None
    assert reloaded.green_headline.predicted_strategy_stops is None
    assert reloaded.green_headline.stop_window_laps is None
    assert reloaded.green_headline_averaged.races_with_predicted_strategy_stops is None
    text = format_backtest(reloaded)
    assert "Stop Window hits on predicted Strategies: not recorded" in text
    assert "Average Stop Window width: not recorded" in text
    # The existing figure still reads as before.
    assert "Stop Window hits: 2/4 actual stops" in text


def test_a_version_3_file_without_the_figures_is_refused(tmp_path):
    wk, _ = _race()
    path = _saved(tmp_path, _run({(2024, "Alpha GP"): wk}), "broken")
    data = json.loads(path.read_text())
    del data["races"][0]["stop_window_laps"]
    path.write_text(json.dumps(data))

    with pytest.raises(KeyError):
        load_backtest_result(path)


_COMMITTED = sorted(_REPO_RESULTS.glob("*.json"))


@pytest.mark.parametrize("path", _COMMITTED, ids=lambda p: p.name)
def test_committed_results_load_with_the_figures_not_recorded(path):
    reloaded, metadata = load_backtest_result(path)

    assert metadata.format_version < 3
    assert all(r.predicted_strategy_stops is None for r in reloaded.races)
    assert "Stop Window hits on predicted Strategies: not recorded" in (
        format_backtest(reloaded)
    )


def test_the_committed_results_compare_cleanly_with_each_other_and_a_new_file(
    tmp_path,
):
    assert len(_COMMITTED) >= 2
    loaded = [load_backtest_result(path) for path in _COMMITTED]
    wk, _ = _race()
    new = load_backtest_result(_saved(tmp_path, _run({(2024, "Alpha GP"): wk}), "new"))

    for (before, bmd), (after, amd) in [
        (loaded[0], loaded[1]),
        (loaded[-1], new),
        (new, loaded[-1]),
    ]:
        comp = compare_backtest_results(
            before, after, before_metadata=bmd, after_metadata=amd
        )
        text = format_comparison(comp)
        assert "not recorded" in text
        assert any("predicted Strategies" in w for w in comp.warnings)


# ---------------------------------------------------------------------------
# Comparing
# ---------------------------------------------------------------------------


def _before_and_after(tmp_path):
    # Before: LEC off the Candidates. After: LEC on one, missing its window,
    # so the hit rate over Predicted-Strategy Stops falls and the width moves.
    before_wk, before_expected = _race(circuit="Alpha")
    after_wk, after_expected = _race(circuit="Alpha", lec_on_candidate=True)
    before = load_backtest_result(
        _saved(tmp_path, _run({(2024, "Alpha GP"): before_wk}), "before")
    )
    after = load_backtest_result(
        _saved(tmp_path, _run({(2024, "Alpha GP"): after_wk}), "after")
    )
    return before, after, before_expected, after_expected


def test_compare_shows_the_change_in_both_figures_for_every_bucket(tmp_path):
    (before, bmd), (after, amd), b, a = _before_and_after(tmp_path)

    comp = compare_backtest_results(
        before, after, before_metadata=bmd, after_metadata=amd
    )

    b_hits, b_stops, b_laps, _ = b
    a_hits, a_stops, a_laps, _ = a
    green = comp.pooled[0]
    assert green.predicted_strategy_stop_window.before_numerator == b_hits
    assert green.predicted_strategy_stop_window.before_denominator == b_stops
    assert green.predicted_strategy_stop_window.after_denominator == a_stops
    assert green.predicted_strategy_stop_window.change_pp == pytest.approx(
        a_hits / a_stops - b_hits / b_stops
    )
    assert green.stop_window_width.before_total == b_laps
    assert green.stop_window_width.before_count == b_stops
    assert green.stop_window_width.change_laps == pytest.approx(
        a_laps / a_stops - b_laps / b_stops
    )
    averaged = comp.averaged[0]
    assert averaged.predicted_strategy_stop_window.change_pp == pytest.approx(
        a_hits / a_stops - b_hits / b_stops
    )
    assert averaged.stop_window_width.change_laps == pytest.approx(
        a_laps / a_stops - b_laps / b_stops
    )
    for breakdown in (comp.by_season[2024], comp.by_circuit["Alpha"]):
        assert breakdown.predicted_strategy_stop_window.after_denominator == a_stops
        assert breakdown.stop_window_width.after_total == a_laps
    # The existing figure's diff is unchanged: hits over every actual stop.
    assert green.stop_window.before_denominator == 4
    assert green.stop_window.label == "Stop Window hits"
    assert comp.warnings == ()


def test_formatted_comparison_shows_both_figures_change(tmp_path):
    (before, bmd), (after, amd), b, a = _before_and_after(tmp_path)

    text = format_comparison(
        compare_backtest_results(
            before, after, before_metadata=bmd, after_metadata=amd
        )
    )

    b_hits, b_stops, b_laps, _ = b
    a_hits, a_stops, a_laps, _ = a
    assert (
        f"Stop Window hits on predicted Strategies: {b_hits}/{b_stops} "
        f"({b_hits / b_stops:.0%}) → {a_hits}/{a_stops} ({a_hits / a_stops:.0%})"
    ) in text
    change = a_laps / a_stops - b_laps / b_stops
    assert (
        f"Average Stop Window width: {b_laps / b_stops:.1f} laps over {b_stops} "
        f"stops → {a_laps / a_stops:.1f} laps over {a_stops} stops "
        f"({change:+.1f} laps)"
    ) in text
    averaged = text.split("Headline (race-averaged):")[1].split("\n\n")[0]
    assert "Average Stop Window width: mean" in averaged
    assert "Stop Window hits on predicted Strategies: mean" in averaged


def test_compare_says_so_when_an_older_result_does_not_have_the_figures(tmp_path):
    (before, _), (after, amd), _, _ = _before_and_after(tmp_path)
    old_path = tmp_path / "old.json"
    old_path.write_text(
        json.dumps(json.loads(next(tmp_path.glob("*_before.json")).read_text()))
    )
    _rewrite_as_version_2(old_path)
    old, omd = load_backtest_result(old_path)

    comp = compare_backtest_results(old, after, before_metadata=omd, after_metadata=amd)
    text = format_comparison(comp)

    assert comp.pooled[0].predicted_strategy_stop_window is None
    assert comp.pooled[0].stop_window_width is None
    assert comp.averaged[0].stop_window_width is None
    assert comp.by_circuit["Alpha"].predicted_strategy_stop_window is None
    assert [w for w in comp.warnings if "predicted Strategies" in w] == [
        "Stop Window hits on predicted Strategies and Stop Window width can't be "
        "compared: before was saved in format version 2, which didn't record them"
    ]
    assert "Stop Window hits on predicted Strategies: not recorded in before" in text
    assert "Average Stop Window width: not recorded in before" in text
    # The existing figure still compares.
    assert comp.pooled[0].stop_window.change_pp is not None
