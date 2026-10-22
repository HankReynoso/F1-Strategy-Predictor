"""Seam 1b: comparing two Backtest Results.

All tests go through the public `compare_backtest_results` call with
hand-built Backtest Results, round-tripped through `save_backtest_result`
and `load_backtest_result` so the compare path reads the same files the
command does.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from weekend_builder import TEAMS, standard_practice, weekend

from f1_strategy import (
    Compound,
    ExcludedRace,
    ExclusionReason,
    RaceSpec,
    RaceWeekend,
    RaceOutcome,
    RunMetadata,
    Stint,
    load_backtest_result,
    predict,
    run_backtest,
    save_backtest_result,
)
from f1_strategy.backtest_compare import (
    BacktestComparison,
    compare_backtest_results,
    format_comparison,
)
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


def _green(
    season: int = 2024,
    circuit: str = "Alpha",
    is_sprint_weekend: bool = False,
    scoreable_driver: str = "VER",
    match: bool = True,
) -> RaceWeekend:
    """A hand-built green weekend. `match=True` → VER's actual Strategy is a
    top candidate; `match=False` → VER runs the S → H → M 2-stop that is
    never the top pick in `standard_practice` (same construction as
    `miss_weekend` in `test_backtest.py`).
    """
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
    if match:
        top = predict(base)[scoreable_driver].candidates[0]
        stop_lap = top.stops[0].best_lap
        return _with_race(
            base,
            stints=[
                Stint(scoreable_driver, top.strategy.compounds[0], 1, stop_lap),
                Stint(scoreable_driver, top.strategy.compounds[1], stop_lap + 1, 57),
            ],
        )
    return _with_race(
        base,
        stints=[
            Stint(scoreable_driver, S, 1, 15),
            Stint(scoreable_driver, H, 16, 40),
            Stint(scoreable_driver, M, 41, 57),
        ],
    )


def _metadata(seasons=(2024,), label="run", **kwargs) -> RunMetadata:
    return RunMetadata(
        label=label,
        run_at="2026-10-21T18:30:00+00:00",
        code_commit="abc123def456",
        uncommitted_changes=False,
        seasons_in_scope=tuple(seasons),
        settings=kwargs.get("settings", Settings()),
    )


def _loader(mapping: dict[tuple[int, str], RaceWeekend]):
    def load(season: int, event: str) -> RaceWeekend:
        return mapping[(season, event)]

    return load


def _run_and_save(tmp_path: Path, weekends, label: str, metadata=None):
    specs = [RaceSpec(s, e) for (s, e) in weekends]
    result = run_backtest(specs, load=_loader(weekends))
    metadata = metadata or _metadata(label=label)
    paths = save_backtest_result(result, tmp_path, metadata=metadata)
    return paths.data


# ---------------------------------------------------------------------------
# Headline score changes
# ---------------------------------------------------------------------------


def test_pooled_and_averaged_headlines_report_before_after_and_change(tmp_path):
    # before: one race, scoreable driver's actual strategy matches the top
    # candidate (full top-1 credit). after: same race, the actual run flips
    # the Compound order so top-1 credit is 0.
    before_wk = {(2024, "Alpha GP"): _green(circuit="Alpha", match=True)}
    after_wk = {(2024, "Alpha GP"): _green(circuit="Alpha", match=False)}
    before, before_md = load_backtest_result(_run_and_save(tmp_path, before_wk, "before"))
    after, after_md = load_backtest_result(_run_and_save(tmp_path, after_wk, "after"))

    comp = compare_backtest_results(
        before, after, before_metadata=before_md, after_metadata=after_md
    )

    [green_pooled, *_] = comp.pooled
    assert green_pooled.label == "Green-race headline"
    assert green_pooled.top_1.before_denominator > 0
    assert green_pooled.top_1.after_denominator > 0
    # Flipping the actual Compound order dropped top-1 credit; the change
    # is the difference in the pooled rate.
    assert green_pooled.top_1.before_numerator > green_pooled.top_1.after_numerator
    assert green_pooled.top_1.change_pp == pytest.approx(
        green_pooled.top_1.after_pct - green_pooled.top_1.before_pct
    )
    assert green_pooled.top_1.change_pp < 0

    [green_averaged, *_] = comp.averaged
    assert green_averaged.label == "Green-race headline"
    assert green_averaged.top_1.before_mean is not None
    assert green_averaged.top_1.after_mean is not None
    assert green_averaged.top_1.change_pp == pytest.approx(
        green_averaged.top_1.after_mean - green_averaged.top_1.before_mean
    )
    assert green_averaged.top_1.before_races == 1
    assert green_averaged.top_1.after_races == 1


def test_breakdowns_show_before_after_and_change_per_group(tmp_path):
    before_wk = {
        (2024, "Alpha GP"): _green(circuit="Alpha", match=True),
        (2024, "Beta GP"): _green(circuit="Beta", match=True),
        (2025, "Delta GP"): _green(season=2025, circuit="Delta", match=False),
    }
    after_wk = {
        (2024, "Alpha GP"): _green(circuit="Alpha", match=False),
        (2024, "Beta GP"): _green(circuit="Beta", match=True),
        (2025, "Delta GP"): _green(season=2025, circuit="Delta", match=True),
    }
    before, bmd = load_backtest_result(_run_and_save(tmp_path, before_wk, "b"))
    after, amd = load_backtest_result(_run_and_save(tmp_path, after_wk, "a"))

    comp = compare_backtest_results(before, after, before_metadata=bmd, after_metadata=amd)

    # 2024: Alpha flipped from match→no-match (goes down), Beta stayed.
    # Pooled change should be negative.
    season_2024 = comp.by_season[2024]
    assert season_2024.top_1.change_pp < 0
    # 2025: Delta flipped from no-match→match (goes up).
    season_2025 = comp.by_season[2025]
    assert season_2025.top_1.change_pp > 0
    # Per-circuit directions align: Alpha down, Beta flat, Delta up.
    assert comp.by_circuit["Alpha"].top_1.change_pp < 0
    assert comp.by_circuit["Beta"].top_1.change_pp == pytest.approx(0.0)
    assert comp.by_circuit["Delta"].top_1.change_pp > 0


def test_breakdown_key_present_on_only_one_side_is_reported_not_crashed(tmp_path):
    before_wk = {
        (2024, "Alpha GP"): _green(circuit="Alpha", match=True),
    }
    after_wk = {
        (2024, "Alpha GP"): _green(circuit="Alpha", match=True),
        (2024, "Beta GP"): _green(circuit="Beta", match=True),
    }
    before, bmd = load_backtest_result(_run_and_save(tmp_path, before_wk, "b"))
    after, amd = load_backtest_result(_run_and_save(tmp_path, after_wk, "a"))

    comp = compare_backtest_results(before, after, before_metadata=bmd, after_metadata=amd)

    # Beta appears in `after` only — the before side has an empty bucket.
    beta = comp.by_circuit["Beta"]
    assert beta.top_1.before_denominator == 0
    assert beta.top_1.before_pct is None
    assert beta.top_1.after_denominator > 0


# ---------------------------------------------------------------------------
# Biggest-moving races
# ---------------------------------------------------------------------------


def test_biggest_moving_races_in_each_direction_are_listed(tmp_path):
    before_wk = {
        (2024, "Alpha GP"): _green(circuit="Alpha", match=True),
        (2024, "Beta GP"): _green(circuit="Beta", match=False),
        (2024, "Gamma GP"): _green(circuit="Gamma", match=True),
    }
    after_wk = {
        (2024, "Alpha GP"): _green(circuit="Alpha", match=False),  # down
        (2024, "Beta GP"): _green(circuit="Beta", match=True),     # up
        (2024, "Gamma GP"): _green(circuit="Gamma", match=True),   # stayed
    }
    before, _ = load_backtest_result(_run_and_save(tmp_path, before_wk, "b"))
    after, _ = load_backtest_result(_run_and_save(tmp_path, after_wk, "a"))

    comp = compare_backtest_results(before, after)

    gainers = [(m.season, m.event) for m in comp.top_gainers]
    losers = [(m.season, m.event) for m in comp.top_losers]
    assert gainers == [(2024, "Beta GP")]
    assert losers == [(2024, "Alpha GP")]
    # Each movement carries its rates and the pp change.
    beta = comp.top_gainers[0]
    assert beta.after_rate > beta.before_rate
    assert beta.change_pp == pytest.approx(beta.after_rate - beta.before_rate)
    assert beta.change_pp > 0


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------


def test_different_seasons_in_scope_produce_a_warning(tmp_path):
    wk = {(2024, "Alpha GP"): _green(circuit="Alpha", match=True)}
    before, bmd = load_backtest_result(
        _run_and_save(tmp_path, wk, "b", metadata=_metadata(seasons=(2024,), label="b"))
    )
    after, amd = load_backtest_result(
        _run_and_save(
            tmp_path,
            wk,
            "a",
            metadata=_metadata(seasons=(2024, 2025), label="a"),
        )
    )

    comp = compare_backtest_results(before, after, before_metadata=bmd, after_metadata=amd)

    assert any("Seasons in scope differ" in w for w in comp.warnings)


def test_different_scored_races_produce_a_warning(tmp_path):
    before_wk = {(2024, "Alpha GP"): _green(circuit="Alpha", match=True)}
    after_wk = {
        (2024, "Alpha GP"): _green(circuit="Alpha", match=True),
        (2024, "Beta GP"): _green(circuit="Beta", match=True),
    }
    before, _ = load_backtest_result(_run_and_save(tmp_path, before_wk, "b"))
    after, _ = load_backtest_result(_run_and_save(tmp_path, after_wk, "a"))

    comp = compare_backtest_results(before, after)

    assert any("Scored races differ" in w for w in comp.warnings)
    assert any("Beta GP" in w for w in comp.warnings)


def test_different_excluded_races_produce_a_warning(tmp_path):
    # Both runs score the same race, but a different wet race joins the
    # excluded list on each side.
    def wet(circuit):
        base = weekend(standard_practice(), TEAMS)
        base = replace(base, pre_race=replace(base.pre_race, circuit=circuit))
        return _with_race(
            base,
            stints=[
                Stint("VER", Compound.INTERMEDIATE, 1, 20),
                Stint("VER", Compound.MEDIUM, 21, 57),
            ],
        )

    before_wk = {
        (2024, "Alpha GP"): _green(circuit="Alpha", match=True),
        (2024, "wet-one"): wet("Zed-One"),
    }
    after_wk = {
        (2024, "Alpha GP"): _green(circuit="Alpha", match=True),
        (2024, "wet-two"): wet("Zed-Two"),
    }
    before, _ = load_backtest_result(_run_and_save(tmp_path, before_wk, "b"))
    after, _ = load_backtest_result(_run_and_save(tmp_path, after_wk, "a"))

    comp = compare_backtest_results(before, after)

    assert any("Excluded Races differ" in w for w in comp.warnings)


def test_different_held_out_season_produces_a_warning(tmp_path):
    wk = {(2024, "Alpha GP"): _green(circuit="Alpha", match=True)}
    before = _run_and_save(
        tmp_path,
        wk,
        "b",
        metadata=_metadata(label="b", settings=Settings(held_out_season=2025)),
    )
    after = _run_and_save(
        tmp_path,
        wk,
        "a",
        metadata=_metadata(label="a", settings=Settings(held_out_season=2024)),
    )
    b_result, bmd = load_backtest_result(before)
    a_result, amd = load_backtest_result(after)

    comp = compare_backtest_results(
        b_result, a_result, before_metadata=bmd, after_metadata=amd
    )

    assert any("Held-out Season differs" in w for w in comp.warnings)


def test_different_tuning_seasons_produces_a_warning(tmp_path):
    wk = {(2024, "Alpha GP"): _green(circuit="Alpha", match=True)}
    before = _run_and_save(
        tmp_path,
        wk,
        "b",
        metadata=_metadata(
            label="b", settings=Settings(tuning_seasons=(2022, 2023, 2024))
        ),
    )
    after = _run_and_save(
        tmp_path,
        wk,
        "a",
        metadata=_metadata(
            label="a", settings=Settings(tuning_seasons=(2022, 2023))
        ),
    )
    b_result, bmd = load_backtest_result(before)
    a_result, amd = load_backtest_result(after)

    comp = compare_backtest_results(
        b_result, a_result, before_metadata=bmd, after_metadata=amd
    )

    assert any("Tuning Seasons differ" in w for w in comp.warnings)


def test_different_estimated_pit_loss_races_produce_a_warning(tmp_path):
    # Same scored race in both runs, but the Pit Loss provenance flipped
    # from measured to estimated. Comparing the two races' numbers isn't
    # apples-to-apples, so the compare warns.
    before_wk = {(2024, "Alpha GP"): _green(circuit="Alpha", match=True)}
    before_result = run_backtest(
        [RaceSpec(2024, "Alpha GP")], load=_loader(before_wk)
    )
    # Flip the flag on the saved record.
    estimated_race = replace(before_result.races[0], estimated_pit_loss=True)
    before_result_flipped = replace(before_result, races=(estimated_race,))

    before_paths = save_backtest_result(
        before_result, tmp_path, metadata=_metadata(label="b")
    )
    after_paths = save_backtest_result(
        before_result_flipped, tmp_path, metadata=_metadata(label="a")
    )
    before, bmd = load_backtest_result(before_paths.data)
    after, amd = load_backtest_result(after_paths.data)

    comp = compare_backtest_results(
        before, after, before_metadata=bmd, after_metadata=amd
    )

    assert any(
        "estimated Pit Loss" in w and "Alpha GP" in w for w in comp.warnings
    )


def test_identical_results_produce_no_warnings(tmp_path):
    wk = {(2024, "Alpha GP"): _green(circuit="Alpha", match=True)}
    before, bmd = load_backtest_result(_run_and_save(tmp_path, wk, "b"))
    after, amd = load_backtest_result(_run_and_save(tmp_path, wk, "a"))

    comp = compare_backtest_results(
        before, after, before_metadata=bmd, after_metadata=amd
    )

    assert comp.warnings == ()


# ---------------------------------------------------------------------------
# Format
# ---------------------------------------------------------------------------


def test_format_comparison_lists_headlines_breakdowns_movers_and_warnings(tmp_path):
    before_wk = {
        (2024, "Alpha GP"): _green(circuit="Alpha", match=True),
        (2024, "Beta GP"): _green(circuit="Beta", match=False),
    }
    after_wk = {
        (2024, "Alpha GP"): _green(circuit="Alpha", match=False),
        (2024, "Beta GP"): _green(circuit="Beta", match=True),
    }
    before = _run_and_save(
        tmp_path,
        before_wk,
        "b",
        metadata=_metadata(seasons=(2024,), label="b"),
    )
    after = _run_and_save(
        tmp_path,
        after_wk,
        "a",
        metadata=_metadata(seasons=(2024, 2025), label="a"),
    )
    b_result, bmd = load_backtest_result(before)
    a_result, amd = load_backtest_result(after)
    comp = compare_backtest_results(
        b_result, a_result, before_metadata=bmd, after_metadata=amd
    )
    text = format_comparison(comp)

    assert "Headline (pooled)" in text
    assert "Headline (race-averaged)" in text
    assert "By season" in text
    assert "By circuit" in text
    assert "Biggest gainers" in text
    assert "Biggest losers" in text
    assert "Beta GP" in text
    assert "WARNINGS" in text
    assert "Seasons in scope differ" in text


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_command_compare_mode_prints_comparison_of_two_saved_results(
    tmp_path, capsys, monkeypatch
):
    before_wk = {(2024, "Alpha GP"): _green(circuit="Alpha", match=True)}
    after_wk = {(2024, "Alpha GP"): _green(circuit="Alpha", match=False)}
    before = _run_and_save(tmp_path, before_wk, "before")
    after = _run_and_save(tmp_path, after_wk, "after")

    exit_code = main(["compare", str(before), str(after)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Headline (pooled)" in captured.out
    assert "Top-1 Strategy Match" in captured.out
    # The top-1 line between the two runs went down; the formatted change
    # is a negative pp figure.
    assert "pp)" in captured.out
