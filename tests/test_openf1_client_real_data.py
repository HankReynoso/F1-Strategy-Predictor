"""Slow real-data test for the OpenF1 HTTP client (ticket 20).

One request against the live ``api.openf1.org/v1/`` endpoint, through
the default ``urllib`` http seam and the real rate limiter. The fast
suite does all shape coverage; this test only pins that the real
network path reaches OpenF1 and returns parseable JSON. The sampled
response matches a shape used in ticket 18's `openf1-findings.md`:
``GET /v1/meetings?year=2024&country_name=Italy`` → one row for Monza.
"""

from __future__ import annotations

import pytest

from f1_strategy.openf1_client import OpenF1Client

pytestmark = pytest.mark.slow


def test_real_meetings_fetch_returns_monza_2024(tmp_path):
    client = OpenF1Client(cache_dir=tmp_path / "openf1")
    meetings = client.get("meetings", year=2024, country_name="Italy")

    # Italy 2024 has one meeting: the Italian GP at Monza. If OpenF1's
    # schema ever grows a second Italian round we only need `location`
    # to include "Monza" to count the test as a pass.
    assert isinstance(meetings, list)
    assert len(meetings) >= 1
    locations = {m.get("location") for m in meetings}
    assert "Monza" in locations

    # A second fetch for the same URL must come from cache: no network
    # cost, no rate-limit cost. We can only check via the request count
    # in a fast test; here we at least pin that the second call returns
    # the same payload.
    again = client.get("meetings", year=2024, country_name="Italy")
    assert again == meetings
