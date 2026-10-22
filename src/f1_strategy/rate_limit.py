"""Wait out FastF1's hourly request limit instead of excluding races.

FastF1 3.8 enforces at most 500 uncached API calls per hour against the
general live-timing APIs (plus a tighter 200/h on ergast.com) with a
sliding one-hour window inside
``fastf1.req._SessionWithRateLimiting._RATE_LIMITS``. Once 500 uncached
requests have landed inside the last hour, the next request raises
``fastf1.exceptions.RateLimitExceededError`` — a ``FastF1CriticalError``
that propagates through ``Session.load()`` instead of being logged.

Cached requests do not count: the shared session wraps
``requests_cache.CacheMixin`` ahead of the rate-limiting
``requests.Session``, so a cache hit short-circuits ``send()`` before the
limiter is consulted. A warm-cache re-run therefore never waits.

This module exposes:

- ``WAIT_SECONDS_DEFAULT`` — how long to sleep on a rate-limit hit, chosen
  so the sliding window has fully elapsed since the first of the past 500
  calls (one hour is the maximum the sliding window ever requires).
- ``default_wait(seconds, reason)`` — the real wait used by
  ``run_backtest`` by default. Prints a message to stderr naming roughly
  when it will resume, then ``time.sleep``s. Tests inject a fake wait so
  no test actually sleeps.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from datetime import datetime, timedelta


# One hour is the maximum the sliding window ever requires between the
# first of the last 500 requests and now; waiting a full hour guarantees
# at least one slot has freed up without having to introspect FastF1's
# internal rate limiter.
WAIT_SECONDS_DEFAULT: float = 60 * 60.0


RateLimitWait = Callable[[float, str], None]


def default_wait(seconds: float, reason: str) -> None:
    """The real wait used by ``run_backtest`` when nothing is injected.

    Prints the reason and a rough resume time to stderr, then sleeps.
    """
    resume_at = datetime.now() + timedelta(seconds=seconds)
    print(
        f"  {reason}; waiting {seconds / 60:.0f} min "
        f"(resuming around {resume_at.strftime('%H:%M:%S')})",
        file=sys.stderr,
        flush=True,
    )
    time.sleep(seconds)
