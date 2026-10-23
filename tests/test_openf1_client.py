"""Fast tests for the OpenF1 HTTP client (ticket 20).

The client wraps `https://api.openf1.org/v1/` with the free-tier rate
limit (3 req/s, 30 req/min), an on-disk JSON cache keyed by request URL,
and retry/backoff on 429 and 5xx responses. These tests drive the public
`OpenF1Client` through a fake HTTP layer and a fake wait so no test
touches the network or really sleeps. A slow test that makes a real
request lives in `test_openf1_client_real_data.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from f1_strategy.openf1_client import (
    BASE_URL,
    MAX_REQUESTS_PER_MINUTE,
    MAX_REQUESTS_PER_SECOND,
    HttpResponse,
    OpenF1Client,
    OpenF1FetchError,
)


class _FakeHttp:
    """Programmable fake for the client's http_get seam.

    Each call pulls the next scripted response and records the url. The
    script can be a list of `HttpResponse` or a callable `url -> HttpResponse`.
    """

    def __init__(self, responses):
        self._responses = responses
        self.calls: list[str] = []

    def __call__(self, url: str) -> HttpResponse:
        self.calls.append(url)
        if callable(self._responses):
            return self._responses(url)
        if not self._responses:
            raise AssertionError(f"no scripted response for {url}")
        return self._responses.pop(0)


class _FakeClock:
    """Monotonic clock whose only movement comes from the fake wait."""

    def __init__(self, start: float = 0.0):
        self.now = start
        self.waits: list[tuple[float, str]] = []

    def read(self) -> float:
        return self.now

    def wait(self, seconds: float, reason: str) -> None:
        self.waits.append((seconds, reason))
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _ok(body) -> HttpResponse:
    return HttpResponse(status=200, body=json.dumps(body).encode(), headers={})


def _http_error(status: int, headers: dict[str, str] | None = None) -> HttpResponse:
    return HttpResponse(status=status, body=b"", headers=headers or {})


def _client(tmp_path: Path, http, clock: _FakeClock, **kwargs) -> OpenF1Client:
    return OpenF1Client(
        cache_dir=tmp_path / "openf1",
        http_get=http,
        wait=clock.wait,
        clock=clock.read,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Fetching: endpoint + query params → parsed JSON list.
# ---------------------------------------------------------------------------


def test_get_builds_url_with_query_parameters_and_returns_parsed_json(tmp_path):
    http = _FakeHttp([_ok([{"meeting_key": 1244, "location": "Monza"}])])
    clock = _FakeClock()

    client = _client(tmp_path, http, clock)
    data = client.get("meetings", year=2024, country_name="Italy")

    assert data == [{"meeting_key": 1244, "location": "Monza"}]
    assert len(http.calls) == 1
    url = http.calls[0]
    assert url.startswith(f"{BASE_URL}meetings?")
    assert "year=2024" in url
    # Spaces encode as `+` (urlencode default) or `%20`; either works for OpenF1.
    assert "country_name=Italy" in url


def test_get_url_encodes_values_with_spaces(tmp_path):
    http = _FakeHttp([_ok([])])
    clock = _FakeClock()

    client = _client(tmp_path, http, clock)
    client.get("sessions", session_name="Practice 1")

    url = http.calls[0]
    assert "session_name=Practice" in url
    # Space must be encoded, never passed raw.
    assert " " not in url


def test_non_list_response_raises_fetch_error(tmp_path):
    http = _FakeHttp([HttpResponse(status=200, body=b'{"error": "oops"}', headers={})])
    clock = _FakeClock()

    client = _client(tmp_path, http, clock)
    with pytest.raises(OpenF1FetchError):
        client.get("meetings", year=2024)


def test_invalid_json_response_raises_fetch_error(tmp_path):
    http = _FakeHttp([HttpResponse(status=200, body=b"not json", headers={})])
    clock = _FakeClock()

    client = _client(tmp_path, http, clock)
    with pytest.raises(OpenF1FetchError):
        client.get("meetings", year=2024)


# ---------------------------------------------------------------------------
# Caching: keyed by request URL; no network and no rate-limit cost on hit.
# ---------------------------------------------------------------------------


def test_cached_response_makes_no_network_call_on_second_fetch(tmp_path):
    http = _FakeHttp([_ok([{"year": 2024}])])
    clock = _FakeClock()

    client = _client(tmp_path, http, clock)
    first = client.get("meetings", year=2024)
    second = client.get("meetings", year=2024)

    assert first == second == [{"year": 2024}]
    assert len(http.calls) == 1  # second call served from cache


def test_cache_is_keyed_by_url_including_query_params(tmp_path):
    http = _FakeHttp(
        [
            _ok([{"year": 2024}]),
            _ok([{"year": 2025}]),
        ]
    )
    clock = _FakeClock()

    client = _client(tmp_path, http, clock)
    a = client.get("meetings", year=2024)
    b = client.get("meetings", year=2025)
    a_again = client.get("meetings", year=2024)
    b_again = client.get("meetings", year=2025)

    assert a == a_again == [{"year": 2024}]
    assert b == b_again == [{"year": 2025}]
    assert len(http.calls) == 2


def test_cached_responses_do_not_count_toward_the_rate_limit(tmp_path):
    """A cached hit must never cause a wait, even past the per-second cap."""
    http = _FakeHttp([_ok([{"meeting_key": 1}])])
    clock = _FakeClock()

    client = _client(tmp_path, http, clock)
    # Prime the cache with one real request.
    client.get("meetings", year=2024)
    # Many cache hits in zero elapsed time — would blow the 3 req/s cap if counted.
    for _ in range(MAX_REQUESTS_PER_SECOND * 5):
        client.get("meetings", year=2024)

    assert len(http.calls) == 1
    assert clock.waits == []


def test_cache_survives_a_fresh_client_instance(tmp_path):
    """On-disk cache: a new client that points at the same folder reuses files."""
    http_a = _FakeHttp([_ok([{"year": 2024}])])
    clock_a = _FakeClock()
    client_a = _client(tmp_path, http_a, clock_a)
    client_a.get("meetings", year=2024)

    # Different client instance; empty response script would raise if a
    # second network call were attempted.
    http_b = _FakeHttp([])
    clock_b = _FakeClock()
    client_b = _client(tmp_path, http_b, clock_b)
    data = client_b.get("meetings", year=2024)

    assert data == [{"year": 2024}]
    assert http_b.calls == []


def test_cache_directory_is_created_if_absent(tmp_path):
    http = _FakeHttp([_ok([])])
    clock = _FakeClock()
    cache_dir = tmp_path / "nested" / "openf1"
    assert not cache_dir.exists()

    client = OpenF1Client(
        cache_dir=cache_dir, http_get=http, wait=clock.wait, clock=clock.read
    )
    client.get("meetings", year=2024)

    assert cache_dir.exists()


# ---------------------------------------------------------------------------
# Rate limiting: 3 req/s and 30 req/min; injectable wait.
# ---------------------------------------------------------------------------


def test_three_requests_in_one_second_do_not_wait(tmp_path):
    http = _FakeHttp([_ok([]) for _ in range(MAX_REQUESTS_PER_SECOND)])
    clock = _FakeClock()

    client = _client(tmp_path, http, clock)
    for i in range(MAX_REQUESTS_PER_SECOND):
        client.get("meetings", year=2020 + i)

    assert clock.waits == []
    assert len(http.calls) == MAX_REQUESTS_PER_SECOND


def test_fourth_request_within_one_second_waits_for_the_per_second_window(tmp_path):
    """A 4th request inside the same second must wait roughly a second."""
    http = _FakeHttp([_ok([]) for _ in range(MAX_REQUESTS_PER_SECOND + 1)])
    clock = _FakeClock()

    client = _client(tmp_path, http, clock)
    for i in range(MAX_REQUESTS_PER_SECOND + 1):
        client.get("meetings", year=2020 + i)

    assert len(clock.waits) == 1
    waited, reason = clock.waits[0]
    assert 0 < waited <= 1.0
    assert "req/s" in reason or "second" in reason.lower()


def test_per_minute_cap_triggers_a_longer_wait(tmp_path):
    """After 30 requests inside a minute, request 31 must wait for the minute window."""
    http = _FakeHttp([_ok([]) for _ in range(MAX_REQUESTS_PER_MINUTE + 1)])
    clock = _FakeClock()

    client = _client(tmp_path, http, clock)
    for i in range(MAX_REQUESTS_PER_MINUTE):
        client.get("meetings", year=2000 + i)
        # Hand-walk the clock so the per-second cap doesn't dominate.
        clock.advance(0.5)
    # 31st request: the per-second window has long cleared, but the
    # per-minute window still holds 30 recent timestamps.
    client.get("meetings", year=9999)

    minute_waits = [w for w in clock.waits if w[0] > 1.0]
    assert len(minute_waits) == 1
    waited, reason = minute_waits[0]
    assert 1.0 < waited <= 60.0
    assert "req/min" in reason or "minute" in reason.lower()


def test_wait_is_injectable_fast_tests_never_really_sleep(tmp_path):
    """The injected wait must be called instead of time.sleep.

    If this test ever starts taking seconds to run it means the wait seam
    is bypassed and the client is really sleeping.
    """
    http = _FakeHttp([_ok([]) for _ in range(MAX_REQUESTS_PER_SECOND + 2)])
    clock = _FakeClock()

    client = _client(tmp_path, http, clock)
    for i in range(MAX_REQUESTS_PER_SECOND + 2):
        client.get("meetings", year=2000 + i)

    # Two over-the-cap requests → at least one wait recorded.
    assert len(clock.waits) >= 1
    for seconds, _reason in clock.waits:
        assert seconds > 0.0


# ---------------------------------------------------------------------------
# Retries: 429 and 5xx retry with backoff, then raise a clear fetch error.
# ---------------------------------------------------------------------------


def test_429_is_retried_and_eventually_succeeds(tmp_path):
    http = _FakeHttp(
        [
            _http_error(429),
            _ok([{"meeting_key": 1}]),
        ]
    )
    clock = _FakeClock()

    client = _client(tmp_path, http, clock)
    data = client.get("meetings", year=2024)

    assert data == [{"meeting_key": 1}]
    assert len(http.calls) == 2
    # At least one back-off wait recorded (the one after the 429).
    assert any("429" in reason or "backoff" in reason.lower() for _, reason in clock.waits)


def test_5xx_is_retried_and_eventually_succeeds(tmp_path):
    http = _FakeHttp(
        [
            _http_error(503),
            _ok([{"ok": True}]),
        ]
    )
    clock = _FakeClock()

    client = _client(tmp_path, http, clock)
    data = client.get("meetings", year=2024)

    assert data == [{"ok": True}]
    assert len(http.calls) == 2


def test_persistent_5xx_raises_openf1_fetch_error(tmp_path):
    http = _FakeHttp([_http_error(502) for _ in range(5)])
    clock = _FakeClock()

    client = _client(tmp_path, http, clock, max_retries=2)
    with pytest.raises(OpenF1FetchError) as excinfo:
        client.get("meetings", year=2024)

    # The error names the status so a reader can tell network from data.
    assert "502" in str(excinfo.value)
    # 1 initial + max_retries(2) attempts = 3 http calls.
    assert len(http.calls) == 3


def test_persistent_429_raises_openf1_fetch_error(tmp_path):
    http = _FakeHttp([_http_error(429) for _ in range(5)])
    clock = _FakeClock()

    client = _client(tmp_path, http, clock, max_retries=2)
    with pytest.raises(OpenF1FetchError) as excinfo:
        client.get("meetings", year=2024)

    assert "429" in str(excinfo.value)


def test_4xx_other_than_429_raises_without_retrying(tmp_path):
    """A 404 is a real data-shape problem, not a transient fetch failure."""
    http = _FakeHttp([_http_error(404)])
    clock = _FakeClock()

    client = _client(tmp_path, http, clock, max_retries=3)
    with pytest.raises(OpenF1FetchError) as excinfo:
        client.get("meetings", year=1900)

    assert "404" in str(excinfo.value)
    assert len(http.calls) == 1  # no retry


def test_retry_honours_retry_after_header(tmp_path):
    """A `Retry-After: N` header on a 429 steers the back-off wait."""
    http = _FakeHttp(
        [
            _http_error(429, headers={"Retry-After": "7"}),
            _ok([{"ok": True}]),
        ]
    )
    clock = _FakeClock()

    client = _client(tmp_path, http, clock)
    client.get("meetings", year=2024)

    backoff = [w for w in clock.waits if w[1].lower().find("backoff") >= 0 or "429" in w[1]]
    assert any(w[0] >= 7.0 for w in backoff)


def test_failed_fetches_are_not_cached(tmp_path):
    """A persistent 5xx must not pollute the cache: the next call retries."""
    http = _FakeHttp([_http_error(503), _http_error(503), _http_error(503)])
    clock = _FakeClock()

    client = _client(tmp_path, http, clock, max_retries=1)
    with pytest.raises(OpenF1FetchError):
        client.get("meetings", year=2024)

    # New client, new http, should see the request go out again.
    http2 = _FakeHttp([_ok([{"ok": True}])])
    clock2 = _FakeClock()
    client2 = _client(tmp_path, http2, clock2)
    data = client2.get("meetings", year=2024)
    assert data == [{"ok": True}]
    assert len(http2.calls) == 1
