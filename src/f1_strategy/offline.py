"""Offline mode: a run from saved data only (ticket 36).

``--offline`` on the commands reads FastF1's and OpenF1's on-disk caches and
never contacts either source. Whatever isn't in them was never downloaded,
which is reported as such: a race as a ``NOT_DOWNLOADED`` Excluded Race, a
past race or session as a Data Quality Warning. Never as "fetch failed",
"archive refused" or "no clean laps", which an offline run can't observe.
"""

from __future__ import annotations

# The reason given for anything an offline run needed but couldn't find.
NOT_DOWNLOADED_REASON = "not downloaded (an offline run reads only saved data)"


class NotDownloadedError(RuntimeError):
    """Data an offline run needed that isn't in the saved data. Online, the
    same request would have been sent; the Backtest records the race as
    ``NOT_DOWNLOADED``, distinct from a fetch failure or missing data.
    """
