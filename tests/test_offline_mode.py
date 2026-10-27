"""Fast tests for ticket 36: offline mode, a run from saved data only.

``--offline`` on ``backtest``, ``smoke`` and the single-race command reads
only what is already downloaded and never contacts FastF1 or OpenF1. These
tests run the real FastF1 library and the real OpenF1 client against empty
or fixture caches in a temporary directory, with every socket connection
made to fail, so any network request fails the test. No sleeping.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import fastf1
import pytest

from f1_strategy import cli, data, fastf1_loader
from f1_strategy.backtest import ExclusionReason, RaceSpec, run_backtest
from f1_strategy.backtest_io import load_backtest_result
from f1_strategy.offline import NotDownloadedError
from f1_strategy.openf1_client import HttpResponse, OpenF1Client


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "openf1"


@pytest.fixture
def no_network(monkeypatch):
    """Fail, and note, every attempt to open a network connection."""
    attempts: list[object] = []

    def refuse(self, address, *args, **kwargs):
        attempts.append(address)
        raise AssertionError(f"network request to {address!r} in an offline test")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    return attempts


@pytest.fixture(autouse=True)
def restore_fastf1_cache(monkeypatch):
    """Put FastF1's process-wide cache and the loader's record of it back
    as they were, so an offline test never leaves later tests offline."""
    monkeypatch.setattr(fastf1_loader, "_cache_setup", None)
    for name in ("_CACHE_DIR", "_requests_session_cached"):
        monkeypatch.setattr(fastf1.Cache, name, getattr(fastf1.Cache, name))


def _refuse_http(url: str) -> HttpResponse:
    raise AssertionError(f"OpenF1 request for {url} in an offline test")


def _count_enable_cache(monkeypatch) -> list[str]:
    calls: list[str] = []
    real = fastf1.Cache.enable_cache.__func__

    def counting(cls, cache_dir, *args, **kwargs):
        calls.append(cache_dir)
        return real(cls, cache_dir, *args, **kwargs)

    monkeypatch.setattr(fastf1.Cache, "enable_cache", classmethod(counting))
    return calls


def _only_if_cached() -> bool:
    return fastf1.Cache._requests_session_cached.settings.only_if_cached


# -- The OpenF1 client ---------------------------------------------------------


def test_offline_openf1_client_serves_saved_responses(tmp_path):
    online = OpenF1Client(
        cache_dir=tmp_path,
        http_get=lambda url: HttpResponse(200, b'[{"year": 2024}]', {}),
    )
    online.get("meetings", year=2024)

    offline = OpenF1Client(cache_dir=tmp_path, http_get=_refuse_http, offline=True)

    assert offline.get("meetings", year=2024) == [{"year": 2024}]


def test_offline_openf1_client_raises_not_downloaded_for_a_missing_response(tmp_path):
    client = OpenF1Client(cache_dir=tmp_path, http_get=_refuse_http, offline=True)

    with pytest.raises(NotDownloadedError, match="not downloaded"):
        client.get("meetings", year=2024)


# -- FastF1: one cache setup per run, offline mode kept -------------------------


def test_offline_mode_survives_every_fastf1_load(tmp_path, monkeypatch, no_network):
    calls = _count_enable_cache(monkeypatch)
    fastf1_loader.set_up_cache(tmp_path, offline=True)

    for event in ("Spanish Grand Prix", "Italian Grand Prix"):
        with pytest.raises(NotDownloadedError):
            fastf1_loader.load_weekend(2022, event, cache_dir=tmp_path)
        fastf1_loader.load_past_race_samples(2021, "Barcelona", cache_dir=tmp_path)
        assert _only_if_cached()

    assert calls == [str(tmp_path)]
    assert no_network == []


def test_online_set_up_turns_offline_mode_off_again(tmp_path):
    fastf1_loader.set_up_cache(tmp_path, offline=True)
    fastf1_loader.set_up_cache(tmp_path, offline=False)

    assert not _only_if_cached()
    assert not fastf1_loader.is_offline()


def test_a_load_with_another_cache_dir_stays_offline(tmp_path, no_network):
    fastf1_loader.set_up_cache(tmp_path / "a", offline=True)

    fastf1_loader.load_past_race_samples(2021, "Barcelona", cache_dir=tmp_path / "b")

    assert _only_if_cached()
    assert no_network == []


# -- What a missing race or past race says --------------------------------------


def test_missing_fastf1_race_is_excluded_as_not_downloaded(tmp_path, no_network):
    fastf1_loader.set_up_cache(tmp_path, offline=True)

    result = run_backtest(
        [RaceSpec(2022, "Spanish Grand Prix")],
        load=lambda season, event: data.load_weekend(
            season, event, fastf1_cache_dir=tmp_path
        ),
    )

    assert result.races == ()
    (excluded,) = result.excluded
    assert excluded.reason is ExclusionReason.NOT_DOWNLOADED
    assert "archive" not in excluded.detail
    assert no_network == []


def test_missing_openf1_race_is_excluded_as_not_downloaded(tmp_path, no_network):
    client = OpenF1Client(cache_dir=tmp_path, http_get=_refuse_http, offline=True)

    result = run_backtest(
        [RaceSpec(2024, "Italian Grand Prix")],
        load=lambda season, event: data.load_weekend(
            season, event, openf1_client=client
        ),
    )

    (excluded,) = result.excluded
    assert excluded.reason is ExclusionReason.NOT_DOWNLOADED


def test_missing_fastf1_past_race_says_not_downloaded(tmp_path, no_network):
    fastf1_loader.set_up_cache(tmp_path, offline=True)

    samples = fastf1_loader.load_past_race_samples(2021, "Barcelona", cache_dir=tmp_path)

    assert samples.pit_losses == () and samples.stint_rates == ()
    assert "not downloaded" in samples.note
    assert "archive" not in samples.note
    assert "no clean laps" not in samples.note
    assert no_network == []


def test_missing_fastf1_past_race_in_a_refused_season_keeps_the_archive_reason(
    tmp_path, no_network
):
    """2018–2020 are refused by the archive whether or not this run asks
    (ADR-0006), so offline and online say the same thing about them."""
    fastf1_loader.set_up_cache(tmp_path, offline=True)

    samples = fastf1_loader.load_past_race_samples(2019, "Barcelona", cache_dir=tmp_path)

    assert "refused 2018–2020" in samples.note
    assert no_network == []


def test_missing_openf1_past_race_is_a_not_downloaded_warning(tmp_path):
    client = OpenF1Client(cache_dir=tmp_path, http_get=_refuse_http, offline=True)

    _, _, _, _, warnings = data.measure_pit_loss_and_history(
        circuit="Monza",
        race_season=2024,
        openf1_client=client,
        fastf1_load_past_race_samples=lambda *a, **k: _monza_2022_samples(),
        return_warnings=True,
    )

    (warning,) = warnings
    assert warning.startswith("2023 ")
    assert "not downloaded" in warning
    assert "fetch succeeded" not in warning


def _monza_2022_samples():
    from f1_strategy.openf1_loader import PastRaceSamples

    return PastRaceSamples(pit_losses=(24.0,), stint_rates=(), race_id="fastf1 2022 Monza")


def test_missing_fastf1_pre_race_session_says_not_downloaded():
    from f1_strategy.fastf1_errors import FastF1Problems, missing_data_reason

    reason = missing_data_reason("2022 Spain FP3", 2022, FastF1Problems(), offline=True)

    assert "not downloaded" in reason


# -- The commands ---------------------------------------------------------------


def test_backtest_offline_makes_no_requests_and_saves_the_flag(
    tmp_path, monkeypatch, no_network, capsys
):
    monkeypatch.chdir(tmp_path)  # empty .cache/fastf1 and .cache/openf1
    calls = _count_enable_cache(monkeypatch)
    races = {2022: [RaceSpec(2022, "Spanish Grand Prix")], 2024: [RaceSpec(2024, "Italian Grand Prix")]}

    code = cli.main(
        ["backtest", "2022", "2024", "--offline", "--label", "offline-check",
         "--results-dir", str(tmp_path / "results")],
        list_season=lambda season: races[season],
    )

    assert code == 0
    (saved,) = (tmp_path / "results").glob("*.json")
    result, metadata = load_backtest_result(saved)
    assert metadata.offline is True
    assert {e.reason for e in result.excluded} == {ExclusionReason.NOT_DOWNLOADED}
    assert "offline" in (tmp_path / "results" / saved.with_suffix(".md").name).read_text()
    assert len(calls) == 1
    assert no_network == []


def test_smoke_offline_makes_no_requests(tmp_path, monkeypatch, no_network, capsys):
    monkeypatch.chdir(tmp_path)

    assert cli.main(["smoke", "--offline"]) == 0

    assert "not downloaded" in capsys.readouterr().out
    assert no_network == []


def test_single_race_offline_makes_no_requests(tmp_path, monkeypatch, no_network):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(NotDownloadedError):
        cli.main(["2022", "Spanish Grand Prix", "--offline"])

    assert no_network == []


def test_commands_are_online_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    cli._fastf1_load_and_list()

    assert not _only_if_cached()
    assert not fastf1_loader.is_offline()


def test_an_online_backtest_records_that_it_was_online(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    weekend_free = {2024: []}

    cli.main(
        ["backtest", "2024", "--label", "online", "--results-dir", str(tmp_path)],
        load=lambda season, event: None,
        list_season=lambda season: weekend_free[season],
    )

    (saved,) = tmp_path.glob("*.json")
    assert load_backtest_result(saved)[1].offline is False


def test_a_result_saved_before_offline_mode_loads_as_online(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.main(
        ["backtest", "2024", "--label", "old", "--results-dir", str(tmp_path)],
        load=lambda season, event: None,
        list_season=lambda season: [],
    )
    (saved,) = tmp_path.glob("*.json")
    payload = json.loads(saved.read_text())
    del payload["metadata"]["offline"]
    saved.write_text(json.dumps(payload))

    assert load_backtest_result(saved)[1].offline is False
