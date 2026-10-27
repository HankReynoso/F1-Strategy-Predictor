"""Seam 1b: saving and reading a Backtest Result.

All tests go through the public `save_backtest_result` /
`load_backtest_result` pair with hand-built race weekends and a fake
loader. The invariant: a saved Backtest Result reads back identical,
including every breakdown.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from weekend_builder import TEAMS, standard_practice, weekend

from f1_strategy import (
    BacktestResult,
    Compound,
    DegradationSource,
    ExclusionReason,
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
from f1_strategy.cli import main
from f1_strategy.settings import Settings

S, M, H = Compound.SOFT, Compound.MEDIUM, Compound.HARD


def _with_race(base, *, stints=(), neutralisations=()):
    stints = tuple(stints)
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


def _one_scoreable_green(
    season: int = 2024,
    circuit: str = "Alpha",
    is_sprint_weekend: bool = False,
) -> RaceWeekend:
    base = weekend(standard_practice(), TEAMS)
    base = replace(
        base,
        pre_race=replace(
            base.pre_race,
            season=season,
            circuit=circuit,
            is_sprint_weekend=is_sprint_weekend,
        ),
    )
    top = predict(base)["VER"].candidates[0]
    stop_lap = top.stops[0].best_lap
    return _with_race(
        base,
        stints=[
            Stint("VER", top.strategy.compounds[0], 1, stop_lap),
            Stint("VER", top.strategy.compounds[1], stop_lap + 1, 57),
        ],
    )


def _wet(season: int = 2024, circuit: str = "Alpha") -> RaceWeekend:
    base = weekend(standard_practice(), TEAMS)
    base = replace(
        base, pre_race=replace(base.pre_race, season=season, circuit=circuit)
    )
    return _with_race(
        base,
        stints=[
            Stint("VER", Compound.INTERMEDIATE, 1, 20),
            Stint("VER", M, 21, 57),
        ],
    )


def _make_loader(mapping: dict[tuple[int, str], RaceWeekend]):
    def load(season: int, event: str) -> RaceWeekend:
        return mapping[(season, event)]

    return load


def _metadata(seasons=(2024,), label="baseline") -> RunMetadata:
    return RunMetadata(
        label=label,
        run_at="2026-10-21T18:30:00+00:00",
        code_commit="abc123def456",
        uncommitted_changes=False,
        seasons_in_scope=tuple(seasons),
        settings=Settings(),
    )


def _full_result(tmp_path, *, metadata=None):
    races = [
        RaceSpec(2024, "Alpha GP"),
        RaceSpec(2024, "Beta GP"),
        RaceSpec(2024, "Gamma GP"),
        RaceSpec(2024, "wet"),
        RaceSpec(2025, "Delta GP"),
    ]
    weekends = {
        (2024, "Alpha GP"): _one_scoreable_green(circuit="Alpha"),
        (2024, "Beta GP"): _one_scoreable_green(circuit="Beta", is_sprint_weekend=True),
        (2024, "Gamma GP"): _one_scoreable_green(circuit="Gamma"),
        (2024, "wet"): _wet(),
        (2025, "Delta GP"): _one_scoreable_green(season=2025, circuit="Delta"),
    }
    return run_backtest(races, load=_make_loader(weekends))


# ---------------------------------------------------------------------------
# Round trip
# ---------------------------------------------------------------------------


def test_saved_backtest_result_reads_back_identical(tmp_path):
    result = _full_result(tmp_path)
    metadata = _metadata(seasons=(2024, 2025))

    paths = save_backtest_result(result, tmp_path, metadata=metadata)
    reloaded, reloaded_metadata = load_backtest_result(paths.data)

    assert reloaded_metadata == metadata
    # Every per-race record and Excluded Race survive untouched.
    assert reloaded.races == result.races
    assert reloaded.excluded == result.excluded
    # Every aggregate (pooled, race-averaged, breakdowns, degradation
    # source counts, tuning / held-out, seasons list) is identical.
    assert reloaded.green_headline == result.green_headline
    assert reloaded.neutralised == result.neutralised
    assert reloaded.all_races == result.all_races
    assert reloaded.green_headline_averaged == result.green_headline_averaged
    assert reloaded.neutralised_averaged == result.neutralised_averaged
    assert reloaded.all_races_averaged == result.all_races_averaged
    assert reloaded.by_season == result.by_season
    assert reloaded.by_circuit == result.by_circuit
    assert reloaded.by_sprint_weekend == result.by_sprint_weekend
    assert reloaded.tuning == result.tuning
    assert reloaded.held_out == result.held_out
    assert reloaded.tuning_seasons == result.tuning_seasons
    assert reloaded.held_out_season == result.held_out_season
    assert reloaded.degradation_source_counts == result.degradation_source_counts


def test_estimated_pit_loss_flag_round_trips(tmp_path):
    # Ticket 07 adds an estimated-Pit-Loss flag to each race, plus the
    # per-race Pit Loss figure and the seasons it drew on (empty when
    # estimated). The saver and reader must carry all three through so a
    # saved Result can be read without losing which races rest on an
    # estimate and which seasons the measured ones came from.
    result = _full_result(tmp_path)
    flagged = replace(
        result.races[0],
        estimated_pit_loss=True,
        pit_loss=20.5,
        pit_loss_seasons=(),
    )
    measured = replace(
        result.races[1],
        estimated_pit_loss=False,
        pit_loss=22.1,
        pit_loss_seasons=(2022, 2023),
    )
    result = replace(result, races=(flagged, measured, *result.races[2:]))
    metadata = _metadata()

    paths = save_backtest_result(result, tmp_path, metadata=metadata)
    reloaded, _ = load_backtest_result(paths.data)

    assert reloaded.races[0].estimated_pit_loss is True
    assert reloaded.races[0].pit_loss == pytest.approx(20.5)
    assert reloaded.races[0].pit_loss_seasons == ()
    assert reloaded.races[1].estimated_pit_loss is False
    assert reloaded.races[1].pit_loss == pytest.approx(22.1)
    assert reloaded.races[1].pit_loss_seasons == (2022, 2023)
    assert all(r.estimated_pit_loss is False for r in reloaded.races[1:])


# ---------------------------------------------------------------------------
# Data Quality Warnings (ticket 39)
# ---------------------------------------------------------------------------

_STINTS_WARNING = "Race /v1/stints: dropped 1 of 57 rows with empty lap_start/lap_end"
_HISTORY_WARNING = (
    "2023 Imola: no usable past-race samples "
    "(fetch succeeded with no rows or no clean laps)"
)
_REPO_RESULTS = Path(__file__).resolve().parent.parent / "results" / "backtest"


def _with_warnings(base: RaceWeekend, *warnings: str) -> RaceWeekend:
    return replace(
        base,
        pre_race=replace(base.pre_race, data_quality_warnings=tuple(warnings)),
    )


def _warned_result(*, with_warnings: bool = True) -> BacktestResult:
    # Alpha carries a target-weekend and a history warning (tickets 30 and
    # 28, in the order the loader writes them); Beta carries none.
    alpha = _one_scoreable_green(circuit="Alpha")
    if with_warnings:
        alpha = _with_warnings(alpha, _STINTS_WARNING, _HISTORY_WARNING)
    weekends = {
        (2024, "Alpha GP"): alpha,
        (2024, "Beta GP"): _one_scoreable_green(circuit="Beta"),
    }
    return run_backtest(
        [RaceSpec(2024, "Alpha GP"), RaceSpec(2024, "Beta GP")],
        load=_make_loader(weekends),
    )


def _rewrite_as_version_1(path: Path) -> None:
    """Make a saved file look like one written before ticket 39."""
    data = json.loads(path.read_text())
    data["format_version"] = 1
    for race in data["races"]:
        del race["data_quality_warnings"]
        # Version 3's keys (ticket 58) didn't exist then either.
        del race["predicted_strategy_stops"]
        del race["stop_window_laps"]
    path.write_text(json.dumps(data, indent=2))


def test_data_quality_warnings_read_back_identical(tmp_path):
    result = _warned_result()
    assert _STINTS_WARNING in format_backtest(result)

    paths = save_backtest_result(result, tmp_path, metadata=_metadata())
    reloaded, _ = load_backtest_result(paths.data)

    assert reloaded.races == result.races
    # The summary of a reloaded result is the one the run printed (ADR-0005).
    assert format_backtest(reloaded) == format_backtest(result)


def test_data_quality_warnings_are_saved_per_race_under_their_final_name(tmp_path):
    # Ticket 34 renames the in-code field; the file already uses that name
    # so the rename is not a second format change.
    paths = save_backtest_result(_warned_result(), tmp_path, metadata=_metadata())
    races = json.loads(paths.data.read_text())["races"]

    assert races[0]["data_quality_warnings"] == [_STINTS_WARNING, _HISTORY_WARNING]
    assert races[1]["data_quality_warnings"] == []
    assert all("history_warnings" not in race for race in races)


def test_a_version_1_file_loads_with_no_data_quality_warnings(tmp_path):
    paths = save_backtest_result(_warned_result(), tmp_path, metadata=_metadata())
    _rewrite_as_version_1(paths.data)

    reloaded, reloaded_metadata = load_backtest_result(paths.data)

    # Everything else reads back; the warnings a version-1 file never held
    # read as none, and its Predicted-Strategy Stops as not recorded.
    assert reloaded.races == tuple(
        replace(race, predicted_strategy_stops=None, stop_window_laps=None)
        for race in _warned_result(with_warnings=False).races
    )
    assert "Data quality warnings" not in format_backtest(reloaded)
    assert reloaded_metadata.format_version == 1


def test_a_saved_file_records_its_format_version_on_the_metadata(tmp_path):
    paths = save_backtest_result(_warned_result(), tmp_path, metadata=_metadata())

    _, reloaded_metadata = load_backtest_result(paths.data)

    assert reloaded_metadata.format_version == 3


@pytest.mark.parametrize(
    "path", sorted(_REPO_RESULTS.glob("*.json")), ids=lambda p: p.name
)
def test_committed_backtest_results_still_load(path):
    data = json.loads(path.read_text())

    reloaded, metadata = load_backtest_result(path)

    assert metadata.format_version == data["format_version"]
    assert len(reloaded.races) == len(data["races"])
    assert len(reloaded.excluded) == len(data["excluded"])


# ---------------------------------------------------------------------------
# File layout and naming
# ---------------------------------------------------------------------------


def test_save_writes_a_data_file_and_a_readable_summary_named_by_date_and_label(
    tmp_path,
):
    result = _full_result(tmp_path)
    metadata = _metadata(label="baseline")

    paths = save_backtest_result(result, tmp_path, metadata=metadata)

    assert paths.data.parent == tmp_path
    assert paths.summary.parent == tmp_path
    assert paths.data.name == "2026-10-21_baseline.json"
    assert paths.summary.name == "2026-10-21_baseline.md"
    assert paths.data.exists()
    assert paths.summary.exists()


def test_label_with_spaces_or_slashes_is_safe_in_a_filename(tmp_path):
    result = _full_result(tmp_path)
    metadata = replace(_metadata(), label="circuit tendency/v2")

    paths = save_backtest_result(result, tmp_path, metadata=metadata)

    # No path separator smuggled through; whitespace becomes a dash.
    assert "/" not in paths.data.name
    assert "\\" not in paths.data.name
    assert " " not in paths.data.name
    assert paths.data.exists()


# ---------------------------------------------------------------------------
# Metadata recording
# ---------------------------------------------------------------------------


def test_metadata_records_label_run_time_code_version_and_seasons(tmp_path):
    result = _full_result(tmp_path)
    metadata = RunMetadata(
        label="tuning-pass-1",
        run_at="2026-10-21T18:30:00+00:00",
        code_commit="deadbeefcafe1234",
        uncommitted_changes=True,
        seasons_in_scope=(2022, 2023, 2024, 2025),
        settings=Settings(probability_scale_s=4.0),
    )

    paths = save_backtest_result(result, tmp_path, metadata=metadata)
    data = json.loads(paths.data.read_text())

    assert data["format_version"] == 3
    assert data["metadata"]["label"] == "tuning-pass-1"
    assert data["metadata"]["run_at"] == "2026-10-21T18:30:00+00:00"
    assert data["metadata"]["code_commit"] == "deadbeefcafe1234"
    assert data["metadata"]["uncommitted_changes"] is True
    assert data["metadata"]["seasons_in_scope"] == [2022, 2023, 2024, 2025]
    # Settings fields are round-tripped — a Backtest Result reads back with
    # the same thresholds and the same tuning/held-out partition.
    assert data["metadata"]["settings"]["probability_scale_s"] == 4.0
    assert data["metadata"]["settings"]["tuning_seasons"] == [2022, 2023, 2024]
    assert data["metadata"]["settings"]["held_out_season"] == 2025


def test_settings_round_trip_includes_a_non_default_held_out_season(tmp_path):
    result = _full_result(tmp_path)
    metadata = replace(
        _metadata(),
        settings=Settings(
            tuning_seasons=(2022, 2023, 2025), held_out_season=2024
        ),
    )

    paths = save_backtest_result(result, tmp_path, metadata=metadata)
    _, reloaded_metadata = load_backtest_result(paths.data)

    assert reloaded_metadata.settings.tuning_seasons == (2022, 2023, 2025)
    assert reloaded_metadata.settings.held_out_season == 2024


# ---------------------------------------------------------------------------
# Readable summary
# ---------------------------------------------------------------------------


def test_summary_file_shows_headline_breakdowns_and_excluded_races(tmp_path):
    result = _full_result(tmp_path)
    metadata = _metadata(seasons=(2024, 2025))

    paths = save_backtest_result(result, tmp_path, metadata=metadata)
    text = paths.summary.read_text()

    # Metadata header.
    assert "baseline" in text
    assert "2026-10-21" in text
    assert "abc123def456" in text
    # Headline, breakdowns, Excluded Races (format_backtest output embedded).
    assert "Top-1 Strategy Match" in text
    assert "race-averaged" in text
    assert "By season" in text
    assert "By circuit" in text
    assert "Sprint vs conventional" in text
    assert "Tuning Seasons" in text
    assert "Held-out Season" in text
    assert "Excluded Races: 1" in text
    assert "not a Dry Race" in text


# ---------------------------------------------------------------------------
# Format version guard
# ---------------------------------------------------------------------------


def test_loading_an_unknown_format_version_is_refused(tmp_path):
    result = _full_result(tmp_path)
    metadata = _metadata()
    paths = save_backtest_result(result, tmp_path, metadata=metadata)
    data = json.loads(paths.data.read_text())
    data["format_version"] = 99
    paths.data.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="format_version"):
        load_backtest_result(paths.data)


def test_degradation_source_enum_keys_serialise_as_their_value_strings(tmp_path):
    result = _full_result(tmp_path)
    paths = save_backtest_result(result, tmp_path, metadata=_metadata())
    data = json.loads(paths.data.read_text())

    # No DegradationSource(...) wrappers in the file — enum members encoded
    # as the strings the formatter already uses.
    for race in data["races"]:
        for key in race["degradation_sources"]:
            assert key in {s.value for s in DegradationSource}


def test_excluded_race_reason_serialises_as_its_value_string(tmp_path):
    result = _full_result(tmp_path)
    paths = save_backtest_result(result, tmp_path, metadata=_metadata())
    data = json.loads(paths.data.read_text())

    reasons = {e["reason"] for e in data["excluded"]}
    assert reasons == {ExclusionReason.NOT_DRY_RACE.value}


# ---------------------------------------------------------------------------
# Opt-out: Smoke-Set-style runs don't save by default from the command
# ---------------------------------------------------------------------------


def test_command_backtest_without_a_label_does_not_save_and_only_prints(
    tmp_path, capsys, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    weekends = {
        (2024, "Alpha GP"): _one_scoreable_green(circuit="Alpha"),
    }

    def load(season, event):
        return weekends[(season, event)]

    def list_season(season):
        return [RaceSpec(2024, "Alpha GP")]

    exit_code = main(["backtest", "2024"], load=load, list_season=list_season)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Top-1 Strategy Match" in captured.out
    # No results folder created, no files written.
    assert not (tmp_path / "results").exists()


def test_command_backtest_with_a_label_saves_a_data_and_summary_file(
    tmp_path, capsys, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    weekends = {
        (2024, "Alpha GP"): _one_scoreable_green(circuit="Alpha"),
    }

    def load(season, event):
        return weekends[(season, event)]

    def list_season(season):
        return [RaceSpec(2024, "Alpha GP")]

    exit_code = main(
        [
            "backtest",
            "2024",
            "--label",
            "baseline",
            "--results-dir",
            str(tmp_path / "results"),
        ],
        load=load,
        list_season=list_season,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    saved = list((tmp_path / "results").glob("*_baseline.json"))
    assert len(saved) == 1
    md = saved[0].with_suffix(".md")
    assert md.exists()
    # The command tells the user where it wrote them.
    assert "baseline" in captured.err or "baseline" in captured.out


def test_command_backtest_no_save_overrides_a_label(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    weekends = {
        (2024, "Alpha GP"): _one_scoreable_green(circuit="Alpha"),
    }

    def load(season, event):
        return weekends[(season, event)]

    def list_season(season):
        return [RaceSpec(2024, "Alpha GP")]

    exit_code = main(
        [
            "backtest",
            "2024",
            "--label",
            "baseline",
            "--no-save",
            "--results-dir",
            str(tmp_path / "results"),
        ],
        load=load,
        list_season=list_season,
    )

    assert exit_code == 0
    assert not (tmp_path / "results").exists()
