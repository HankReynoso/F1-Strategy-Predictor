# 20: OpenF1 HTTP client and rate limiter

**What to build:** A thin HTTP client for `https://api.openf1.org/v1/` with the free-tier rate limit (3 req/s and 30 req/min), on-disk JSON cache keyed by request URL, and retry/backoff on 429/5xx. Reuses the `rate_limit.py` wait seam from ticket 17 so the limiter is testable without real sleeps.

**Blocked by:** 19 (ADR)

**Status:** needs-triage

**Category:** enhancement

Scope and the rate-limit numbers come from [`openf1-findings.md`](../openf1-findings.md) ("OpenF1 coverage, terms, limits"). Follow-up from [ticket 18](18-check-openf1-as-second-data-source.md).

**Out of scope:** anything that reads the response payloads into the weekend description — that is tickets 21 and 22.
