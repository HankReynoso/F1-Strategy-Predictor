"""Fast tests for ticket 42: one OpenF1 client for a whole run.

OpenF1's free tier allows 3 requests per second and 30 per minute, and
:class:`.openf1_client.OpenF1Client` keeps to that by remembering when it
made its recent requests. The data router used to build a new client for
every race, so each race started with an empty memory and could burst
straight past the limit set by the race before it.

The CLI's default loader (single race, Smoke Set, Backtest) now builds one
client and passes it to every race, past race and season listing. These
tests run two consecutive races through that loader against a fake OpenF1
server and a fake clock, and check every request's time against the
limits. No network, no sleeping.
"""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import pytest

from f1_strategy import cli, data
from f1_strategy.openf1_client import (
    BASE_URL,
    MAX_REQUESTS_PER_MINUTE,
    MAX_REQUESTS_PER_SECOND,
    HttpResponse,
    OpenF1Client,
)
from f1_strategy.openf1_loader import PastRaceSamples
from f1_strategy.weekend import Compound


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "openf1"


def _fixture_rows() -> dict[str, list[dict]]:
    """Monza and Austria 2024 as one fake server. The two share their
    meeting lists; their rows are merged by meeting key."""
    rows: dict[str, list[dict]] = {}
    for name in ("monza_2024.json", "austria_2024.json"):
        with (FIXTURES / name).open(encoding="utf-8") as f:
            for key, value in json.load(f).items():
                if key.startswith("_"):
                    continue
                if key.startswith("meetings?") and key in rows:
                    known = {r["meeting_key"] for r in rows[key]}
                    rows[key] += [r for r in value if r["meeting_key"] not in known]
                else:
                    rows[key] = value
    return rows


class _FakeOpenF1:
    """A fake clock and a fake OpenF1 server that notes when each request
    reached it. Only the client's own waits move the clock."""

    def __init__(self) -> None:
        self.now = 0.0
        self.request_times: list[float] = []
        self.rows = _fixture_rows()

    def clock(self) -> float:
        return self.now

    def wait(self, seconds: float, _reason: str) -> None:
        self.now += seconds

    def http_get(self, url: str) -> HttpResponse:
        self.request_times.append(self.now)
        parsed = urllib.parse.urlsplit(url)
        endpoint = parsed.path.rsplit("/", 1)[-1]
        query = "&".join(
            f"{k}={v}" for k, v in sorted(urllib.parse.parse_qsl(parsed.query))
        )
        key = f"{endpoint}?{query}" if query else endpoint
        if key not in self.rows:
            return HttpResponse(status=404, body=b'{"detail":"No results found."}', headers={})
        return HttpResponse(status=200, body=json.dumps(self.rows[key]).encode(), headers={})


@pytest.fixture
def server(monkeypatch, tmp_path) -> _FakeOpenF1:
    """Every OpenF1 client the code builds talks to the fake server through
    the fake clock, and is counted. FastF1's 2022 history is stubbed."""
    server = _FakeOpenF1()
    server.clients: list[OpenF1Client] = []

    def build_client(cache_dir=None, **_kwargs) -> OpenF1Client:
        client = OpenF1Client(
            tmp_path / "openf1",
            wait=server.wait,
            http_get=server.http_get,
            clock=server.clock,
        )
        server.clients.append(client)
        return client

    monkeypatch.setattr(data, "OpenF1Client", build_client)
    monkeypatch.setattr(cli, "OpenF1Client", build_client, raising=False)

    def fastf1_2022(season, event, **_kwargs) -> PastRaceSamples:
        return PastRaceSamples(
            pit_losses=(24.0,),
            stint_rates=((Compound.HARD, 0.05, 20),),
            race_id=f"fastf1 {season} {event}",
        )

    monkeypatch.setattr(data.fastf1_loader, "load_past_race_samples", fastf1_2022)
    return server


def _most_in_any_window(times: list[float], window: float) -> int:
    return max(
        sum(1 for t in times if start <= t < start + window) for start in times
    )


def test_two_consecutive_races_stay_within_openf1_limits(server) -> None:
    load = cli._fastf1_load()
    load(2024, "Italian Grand Prix")
    first_race = len(server.request_times)
    load(2024, "Austrian Grand Prix")

    times = server.request_times
    # Both races made requests, more than one second's worth each.
    assert first_race > MAX_REQUESTS_PER_SECOND
    assert len(times) - first_race > MAX_REQUESTS_PER_SECOND
    assert _most_in_any_window(times, 1.0) <= MAX_REQUESTS_PER_SECOND
    assert _most_in_any_window(times, 60.0) <= MAX_REQUESTS_PER_MINUTE
    assert len(server.clients) == 1


def test_the_backtest_loader_and_season_lister_share_one_client(server, monkeypatch) -> None:
    """The Backtest's ``list_season`` uses the same client as its races."""
    seen: list[object] = []

    def record_list_season(season, *, client=None, cache_dir=None):
        seen.append(client)
        return []

    monkeypatch.setattr(data.openf1_loader, "list_season", record_list_season)
    load, list_season = cli._fastf1_load_and_list()
    list_season(2024)
    load(2024, "Italian Grand Prix")
    load(2024, "Austrian Grand Prix")
    assert len(server.clients) == 1
    assert seen == [server.clients[0]]


def test_each_run_gets_its_own_client(server) -> None:
    """One client per run, not one per process: two runs never share
    rate-limit memory or a cache directory they didn't ask for."""
    cli._fastf1_load()(2024, "Italian Grand Prix")
    cli._fastf1_load()(2024, "Austrian Grand Prix")
    assert len(server.clients) == 2
