"""HTTP client for OpenF1 (ticket 20).

A thin layer over ``https://api.openf1.org/v1/`` that respects the free
tier's 3 req/s and 30 req/min caps (``openf1.org`` FAQ, confirmed
2026-10-23), caches successful JSON responses on disk keyed by request
URL, and retries 429 / 5xx with back-off. Turning the responses into the
weekend description is tickets 21 and 22; this module is only about
fetching, caching and rate limiting.

The rate-limit wait uses the same injectable seam as
``src/f1_strategy/rate_limit.py`` so fast tests never really sleep.

Cache layout: one file per request URL, written atomically as JSON. The
filename is the SHA-256 of the URL so a request's cache file is
reproducible from its URL alone. A ``.url`` sidecar is written next to
each payload file so a human reader can tell which cache entry is which
without re-hashing.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .rate_limit import RateLimitWait, default_wait


BASE_URL = "https://api.openf1.org/v1/"

# Free-tier limits, read from the OpenF1 landing page / FAQ on
# 2026-10-23: "Up to 3 requests per second and 30 requests per minute."
MAX_REQUESTS_PER_SECOND = 3
MAX_REQUESTS_PER_MINUTE = 30


class OpenF1FetchError(RuntimeError):
    """A request that still failed after retrying.

    The Backtest turns this into a ``FETCH_FAILED`` Excluded Race (see
    ticket 17's ``ExclusionReason.FETCH_FAILED``), distinct from a
    genuine "data unavailable" case.
    """


@dataclass(frozen=True)
class HttpResponse:
    """Minimal response triple the client works against.

    Decoupled from ``requests``/``urllib`` so tests can script HTTP
    behaviour without a real network stack.
    """

    status: int
    body: bytes
    headers: dict[str, str]


HttpGet = Callable[[str], HttpResponse]


def _default_http_get(url: str) -> HttpResponse:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return HttpResponse(
                status=resp.status,
                body=resp.read(),
                headers={k: v for k, v in resp.headers.items()},
            )
    except urllib.error.HTTPError as e:
        body = e.read() if hasattr(e, "read") else b""
        headers = {k: v for k, v in (e.headers or {}).items()} if e.headers else {}
        return HttpResponse(status=e.code, body=body, headers=headers)


class OpenF1Client:
    """Fetches, caches and rate-limits OpenF1 requests.

    Parameters
    ----------
    cache_dir
        Where to write the on-disk JSON cache. Created if absent.
    wait
        Called as ``wait(seconds, reason)`` whenever the client must
        pause (for the per-second or per-minute cap, or to back off a
        429 / 5xx). Defaults to :func:`rate_limit.default_wait` which
        really sleeps; tests inject a fake.
    http_get
        Called as ``http_get(url) -> HttpResponse``. Defaults to a thin
        ``urllib.request`` wrapper; tests inject a fake.
    clock
        Returns a monotonic time in seconds. Defaults to
        :func:`time.monotonic`; tests inject a fake so timestamps don't
        drift during the test.
    max_retries
        How many extra attempts after the first on a 429 / 5xx before
        raising :class:`OpenF1FetchError`.
    backoff_base
        Base seconds for the exponential back-off used when the server
        does not supply a ``Retry-After`` header. The sequence is
        ``backoff_base * 2 ** attempt``.
    """

    def __init__(
        self,
        cache_dir: Path,
        *,
        wait: RateLimitWait = default_wait,
        http_get: HttpGet = _default_http_get,
        clock: Callable[[], float] = time.monotonic,
        max_retries: int = 3,
        backoff_base: float = 1.0,
    ) -> None:
        self._cache_dir = cache_dir
        self._wait = wait
        self._http_get = http_get
        self._clock = clock
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._second_window: deque[float] = deque()
        self._minute_window: deque[float] = deque()
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, endpoint: str, **params: Any) -> list[dict]:
        """Fetch an endpoint and return the parsed JSON list.

        A cached response is served from disk without touching the
        network or the rate-limit windows. A fresh fetch is cached only
        on success.
        """
        url = self._build_url(endpoint, params)
        cached = self._read_cache(url)
        if cached is not None:
            return cached
        payload = self._fetch_with_retry(url)
        self._write_cache(url, payload)
        return payload

    # -- URL building & cache file layout ----------------------------------

    def _build_url(self, endpoint: str, params: dict[str, Any]) -> str:
        endpoint = endpoint.lstrip("/")
        if not params:
            return f"{BASE_URL}{endpoint}"
        # Sort for deterministic cache keys regardless of kwarg order.
        qs = urllib.parse.urlencode(
            sorted((k, str(v)) for k, v in params.items()),
            quote_via=urllib.parse.quote,
        )
        return f"{BASE_URL}{endpoint}?{qs}"

    def _cache_path(self, url: str) -> Path:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self._cache_dir / f"{key}.json"

    def _read_cache(self, url: str) -> list[dict] | None:
        path = self._cache_path(url)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, list):
            return None
        return data

    def _write_cache(self, url: str, payload: list[dict]) -> None:
        path = self._cache_path(url)
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f)
        tmp.replace(path)
        # Sidecar: lets a human reader tell cache entries apart without
        # re-hashing. Best-effort — a write failure here isn't fatal.
        try:
            path.with_suffix(".url").write_text(url + "\n", encoding="utf-8")
        except OSError:
            pass

    # -- Rate limiting -----------------------------------------------------

    def _wait_for_rate_limit(self) -> None:
        now = self._clock()
        self._evict(now)

        wait_seconds = 0.0
        reason: str | None = None
        if len(self._second_window) >= MAX_REQUESTS_PER_SECOND:
            needed = 1.0 - (now - self._second_window[0])
            if needed > wait_seconds:
                wait_seconds = needed
                reason = (
                    f"OpenF1 free tier ({MAX_REQUESTS_PER_SECOND} req/s)"
                )
        if len(self._minute_window) >= MAX_REQUESTS_PER_MINUTE:
            needed = 60.0 - (now - self._minute_window[0])
            if needed > wait_seconds:
                wait_seconds = needed
                reason = (
                    f"OpenF1 free tier ({MAX_REQUESTS_PER_MINUTE} req/min)"
                )

        if wait_seconds > 0:
            assert reason is not None
            self._wait(wait_seconds, reason)
            self._evict(self._clock())

    def _evict(self, now: float) -> None:
        while self._second_window and now - self._second_window[0] >= 1.0:
            self._second_window.popleft()
        while self._minute_window and now - self._minute_window[0] >= 60.0:
            self._minute_window.popleft()

    def _record_request(self) -> None:
        now = self._clock()
        self._second_window.append(now)
        self._minute_window.append(now)

    # -- Fetch with retry --------------------------------------------------

    def _fetch_with_retry(self, url: str) -> list[dict]:
        last_status: int | None = None
        for attempt in range(self._max_retries + 1):
            self._wait_for_rate_limit()
            response = self._http_get(url)
            self._record_request()

            if 200 <= response.status < 300:
                try:
                    data = json.loads(response.body)
                except json.JSONDecodeError as e:
                    raise OpenF1FetchError(
                        f"{url}: invalid JSON ({e})"
                    ) from e
                if not isinstance(data, list):
                    raise OpenF1FetchError(
                        f"{url}: expected JSON list, got "
                        f"{type(data).__name__}"
                    )
                return data

            last_status = response.status
            retryable = response.status == 429 or 500 <= response.status < 600
            if not retryable or attempt >= self._max_retries:
                break

            delay = self._backoff_delay(response.headers, attempt)
            self._wait(delay, f"OpenF1 {response.status}, backing off")

        raise OpenF1FetchError(
            f"{url}: HTTP {last_status} after {attempt + 1} attempt(s)"
        )

    def _backoff_delay(self, headers: dict[str, str], attempt: int) -> float:
        retry_after = _parse_retry_after(headers)
        if retry_after is not None:
            return retry_after
        return self._backoff_base * (2 ** attempt)


def _parse_retry_after(headers: dict[str, str]) -> float | None:
    for name in ("Retry-After", "retry-after"):
        if name in headers:
            try:
                return float(headers[name])
            except ValueError:
                return None
    return None
