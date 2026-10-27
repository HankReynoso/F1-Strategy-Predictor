"""Telling FastF1's fetch failures apart from genuinely missing data (ticket 40).

FastF1's ``Session.load`` and ``get_event_schedule`` catch almost every
error themselves: they log a warning plus a DEBUG record carrying the
traceback, and return with the data missing. Only ``FastF1CriticalError``
(the rate limit) is raised. So a network outage, an archive that refuses
the request and a session that simply has no data all look the same from
outside: no laps.

:func:`watch_fastf1` records what FastF1 logged during a call, and
:func:`missing_data_reason` turns it into one of three outcomes once the
data is known to be missing:

- a network error raises :class:`FastF1FetchError`, which the Backtest
  records as ``FETCH_FAILED`` (as ticket 28 does for OpenF1);
- FastF1's ``SessionNotAvailableError`` means the archive has no data (or
  refused it, as it does for 2018–2020, ADR-0006): an honest reason;
- anything else gives a reason naming the error.

The rate limit needs none of this: FastF1 raises it, and the loader lets it
through to the Backtest's wait-and-retry (ticket 17).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import requests

# Seasons the live-timing archive refuses without an F1 TV login since
# mid-October 2026 (ADR-0006), named in the reason so a reader knows the
# gap is expected and permanent for now.
ARCHIVE_REFUSED_SEASONS = (2018, 2019, 2020)


class FastF1FetchError(RuntimeError):
    """A FastF1 request that failed on the network, so its data is missing
    for this run only. The Backtest records it as ``FETCH_FAILED``, the same
    as :class:`.openf1_client.OpenF1FetchError`, never as missing data.
    """


class FastF1Problems:
    """The exceptions FastF1 logged (or raised) during one call, by kind."""

    def __init__(self) -> None:
        self.network: list[BaseException] = []
        self.no_data: list[BaseException] = []
        self.other: list[BaseException] = []

    def add(self, error: BaseException) -> None:
        if _is_network_error(error):
            self.network.append(error)
        elif type(error).__name__ == _SESSION_NOT_AVAILABLE:
            self.no_data.append(error)
        else:
            self.other.append(error)


# FastF1 raises this (from its private ``fastf1._api``) when the live-timing
# archive returns nothing for a session: a 401/403 refusal (the archive has
# refused unauthenticated requests since mid-October 2026, ADR-0006) or a
# session it doesn't hold. Matched by name so a FastF1 rename degrades to the
# generic reason instead of an import error; a fast test pins the real class.
_SESSION_NOT_AVAILABLE = "SessionNotAvailableError"


class _Recorder(logging.Handler):
    def __init__(self, problems: FastF1Problems) -> None:
        super().__init__(level=logging.DEBUG)
        self._problems = problems

    def emit(self, record: logging.LogRecord) -> None:
        if record.exc_info and record.exc_info[1] is not None:
            self._problems.add(record.exc_info[1])


@contextmanager
def watch_fastf1() -> Iterator[FastF1Problems]:
    """Record the exceptions FastF1 logs while the ``with`` block runs.

    FastF1's base logger is already at DEBUG, so the traceback records its
    ``soft_exceptions`` wrapper writes reach this handler without changing
    any level.
    """
    problems = FastF1Problems()
    handler = _Recorder(problems)
    logger = logging.getLogger("fastf1")
    logger.addHandler(handler)
    try:
        yield problems
    finally:
        logger.removeHandler(handler)


def missing_data_reason(
    what: str,
    season: int,
    problems: FastF1Problems,
    raised: BaseException | None = None,
) -> str:
    """Why FastF1 left ``what`` without data. Call it only once the data is
    known to be missing: FastF1 also logs harmless side failures (such as the
    Ergast first-lap lookup) on loads that succeed.

    Raises :class:`FastF1FetchError` when a network error was among the
    causes, since the data may well exist. Otherwise returns an honest
    reason for a Data Quality Warning or an Excluded Race's detail.
    """
    if raised is not None:
        problems.add(raised)
    if problems.network:
        cause = problems.network[0]
        raise FastF1FetchError(
            f"{what}: network error ({type(cause).__name__}: {cause})"
        ) from cause
    if problems.no_data:
        reason = "the F1 live-timing archive returned no data for it"
        if season in ARCHIVE_REFUSED_SEASONS:
            reason += (
                f" (it has refused {ARCHIVE_REFUSED_SEASONS[0]}–"
                f"{ARCHIVE_REFUSED_SEASONS[-1]} without an F1 TV login since "
                "mid-October 2026, ADR-0006)"
            )
        return reason
    if raised is not None:
        return f"FastF1 raised {type(raised).__name__}: {raised}"
    if problems.other:
        first = problems.other[0]
        return f"FastF1 loaded no lap data ({type(first).__name__}: {first})"
    return "FastF1 loaded no lap data"


def _is_network_error(error: BaseException) -> bool:
    """A failed request: no connection, a timeout, a dropped response."""
    return isinstance(error, (requests.exceptions.RequestException, ConnectionError, TimeoutError))
