# 61: The committed format-version-3 baseline fails a fast test

**What to build:** Make the fast test suite pass again with `results/backtest/2026-10-27_baseline-v3.json` committed.

**Blocked by:** None

**Status:** needs-triage

**Category:** bug

## Background

Found while building ticket 51. On a clean checkout of `5d4fc08` ("Baseline v3"), `uv run pytest -m "not slow"` gives 1 failure:

```
FAILED tests/test_stop_windows_on_predicted_strategies.py::test_committed_results_load_with_the_figures_not_recorded[2026-10-27_baseline-v3.json]
>       assert metadata.format_version < 3
E       AssertionError: assert 3 < 3
```

Ticket 58 wrote this test to check that every committed Backtest Result reloads with the "not recorded" figures. That was true while every committed result was format version 2. It parametrizes over every `results/backtest/*.json`, so the first committed format-version-3 result (ticket 59's baseline) breaks it.

Options to weigh at triage:

- Limit the test to committed results below format version 3, and add a sibling test that format-version-3 results reload with the figures recorded.
- Pin the test to the two named format-version-2 files instead of globbing.
