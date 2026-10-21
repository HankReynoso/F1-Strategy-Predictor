# 01: Regulation Era as one source of truth

**What to build:** Define the Regulation Era boundaries (2022–2025, then 2026 onward) in one place, and make every historical input read from it. Historical Degradation draws only on earlier seasons in the same Regulation Era as the race being predicted (ADR-0004), replacing today's scattered minimum-season numbers. Pit Loss keeps today's behaviour in this ticket; its pre-era fallback is ticket 03. This is a prefactor: no result for a 2023–2025 race changes. See `../spec.md`.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] The Regulation Era boundaries are defined once, and the loader reads them instead of a hard-coded minimum season
- [x] Historical Degradation for a race uses only earlier seasons in the same Regulation Era
- [x] A 2022 race gets no Historical Degradation (slow test)
- [x] A 2023 race's Historical Degradation uses 2022 only (slow test)
- [x] Singapore 2024 and Monza 2024 single-race results are unchanged
- [x] Tests go through the existing public calls; fast tests need no internet

## Implementation notes

**What was built (2026-10-21), test-first.**

- `src/f1_strategy/regulation_era.py` — one source of truth for Regulation
  Era boundaries. `REGULATION_ERAS` holds `(first_season, last_or_None)`
  tuples (today: `(2022, 2025)` and `(2026, None)`), and two tiny public
  helpers read them: `era_of(season)` returns the era tuple, `era_start(
  season)` returns its first season. Pre-2022 raises so a stray old season
  never silently defaults to the 2022 era.
- `fastf1_loader.load_weekend()` — the `history_min_season` keyword now
  defaults to `None` meaning "use `era_start(season)`". An explicit integer
  still overrides, which the `_pit_loss_at_circuit` back-compat alias and
  the new 2022 slow test need. The hard-coded `2022` is gone. `
  pit_loss_min_season` is deliberately left on 2022 — its proper pre-era
  fallback is ticket 03.
- Tests. Fast: `tests/test_regulation_era.py` covers the three era cases
  (2022–2025 share one era, 2026 starts a new one, pre-2022 raises); no
  internet. Slow: two new real-data tests in `test_fastf1_weekend_loader.
  py` go through `load_weekend` and prove that Monza 2022 returns an empty
  `historical_degradation` dict, and Monza 2023's dict lists only 2022 as
  the contributing season for every Compound. Monza 2022 needs its Pit
  Loss, so the 2022 test passes `pit_loss_min_season=2018` explicitly to
  make the load succeed under today's loader; once ticket 03 lands that
  override can come off.

**Decisions and alternatives rejected.**

- *A single `REGULATION_ERAS` tuple, not a function per era.* The data
  shape is "a list of (start, end) spans"; building that into one list is
  the shape ADR-0004 describes. A function per era would scatter the same
  fact in two places and need another edit every time 2026 ends. The
  pre-2022 case raises rather than silently returning `(2022, 2025)` so
  that an off-by-one in a caller fails loudly.
- *`history_min_season=None` as default, meaning "use the era".* Keeping
  the keyword lets the one slow test override it; dropping the keyword
  altogether would have made the back-compat `_pit_loss_at_circuit`
  internal shim awkward and left no seam for a test like
  `test_pit_loss_never_includes_the_race_being_predicted`. Default of
  `None` resolved at call time, rather than a module-level default, is
  how `datetime.now()` and `pd.read_csv` handle "default means figure it
  out" — it keeps the single source of truth in `regulation_era`.
- *Pit Loss left alone.* The ticket explicitly scopes Pit Loss out ("its
  pre-era fallback is ticket 03"). Changing it here would have mixed two
  decisions and made the "no 2023–2025 result changes" check harder to
  trust. The 2022 slow test loosens `pit_loss_min_season` locally for the
  same reason — this ticket doesn't touch defaults it isn't supposed to.
- *Slow tests go through `load_weekend`, not `_past_races_at_circuit`.*
  Acceptance criterion ("through existing public calls"). Loader internals
  stay free to move.
- *2022 test picks Monza.* Monza 2022 is already covered by the loader's
  existing fixtures (Monza 2024's history uses Monza 2022 and 2023), so
  the cold-download cost is already paid for the shared cache. Any other
  2022 race would have been equally correct and would have slowed the
  test suite.
- *The era list ends 2025 with a concrete integer, not None.* ADR-0004
  says 2026 is a new era because of regulation changes already announced,
  so the boundary is known. Keeping the end open on the current era would
  let a 2026 race silently pool with 2025 if the module were forgotten
  about.

**Deviations from the ticket / spec.** None. The spec's "Loader:
Regulation Era" bullet matched what was built. The 2022 slow test's
`pit_loss_min_season=2018` override is a scope detail, not a deviation —
ticket 03 will make it unneeded by changing the default.

**Baselines, not changing.** Before the loader change, Singapore 2024 and
Monza 2024 outputs were captured by running the CLI (`uv run f1-strategy
2024 "Singapore Grand Prix"` and `… 2024 "Italian Grand Prix"`). After
the change, both runs are byte-identical to the baselines (`diff` empty).
Singapore 2024 Top-1 6.5/18, Top-3 13.75/18, Stop Window hits 3/20;
Monza 2024 Top-1 4/19, Top-3 10/19, Stop Window hits 10/30. These match
the figures recorded in `pre-race-prediction-single-race/issues/08` and
`/issues/11`.

**Known limitations and follow-ups.**

- *Pit Loss default still forces 2022+.* A 2022 race loaded with default
  settings still raises because no pre-2022 race is in range. Ticket 03
  changes that default to use pre-era data (ADR-0004 exception). Until
  then, `load_weekend(2022, …)` needs an explicit `pit_loss_min_season`.
- *First-time-circuit Pit Loss.* Still missing (ticket 07). A race with
  no history and no pit-lane table entry will still fail the load.

**Review feedback for the user.** None — a clean prefactor; no behaviour
change for 2023–2025 races, confirmed on Singapore and Monza 2024.
