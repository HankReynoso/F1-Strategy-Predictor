# 27: Port the slow FastF1 target-weekend tests to the data router (or OpenF1 fixtures)

**What to build:** Migrate the slow tests that still load a 2023+ race through `fastf1_loader.load_weekend` directly off the on-disk FastF1 cache. Since mid-October 2026 F1's live-timing archive returns 401 for unauthenticated clients, the cold path fails with `SessionNotAvailableError` / `DataNotLoadedError`; the ticket-23 router already papers over this for the Backtest and the Smoke Set but these tests bypass it on purpose. The affected tests, as of ticket 23 (2026-10-26):

- `tests/test_fastf1_weekend_loader.py` — every test that loads a 2023+ race as its target weekend (e.g. `test_loads_as_a_race_weekend`, `test_a_2024_races_pit_loss_uses_only_same_era_seasons`, `test_a_2023_races_historical_degradation_uses_2022_only`, `test_miami_gardens_2025_pit_loss_comes_from_miami_same_era`, `test_sprint_weekend_includes_sprint_qualifying_and_the_sprint`, `test_list_season_2024_marks_sprint_weekends`, and the practice/pit/pit-loss/safety-car tests that use 2024 as the sample weekend).
- `tests/test_backtest_real_data.py::test_singapore_2024_backtest_matches_ticket_08_rerun_after_ticket_14` — loads 2024 Singapore directly through `fastf1_loader.load_weekend`.
- `tests/test_singapore_scoreability.py::test_singapore_2024_scores_18_drivers` — same.

Two migration paths per test (pick whichever keeps the test's intent clearest):

1. **Route through the data facade** — replace the `fastf1_loader.load_weekend` import with `f1_strategy.data.load_weekend` and pass both cache dirs. These tests then prove the router works end-to-end on real data; the 2024 target weekend goes through OpenF1 and the past-race scan still touches FastF1 for 2022.
2. **Keep the test on `fastf1_loader` but switch to a cached pre-era weekend** or to a hand-built `RaceWeekend` fixture, when the test is specifically about FastF1's own behaviour at the lap-table layer (e.g. the SC/VSC derivation off `TrackStatus`).

**Blocked by:** 23 (data router).

**Status:** needs-triage

**Category:** test-fix

Follow-up from [ticket 23](23-season-router-and-list-season-port.md) "Slow tests through the router".

## Comments

Discovered 2026-10-26 while running ticket 23's full slow-test sweep. The failing tests were already failing on main — the ticket-23 router makes it visible that the fix is per-test rather than per-loader, because each of these tests is pinning a specific slice of FastF1 behaviour on a 2024 sample weekend.
