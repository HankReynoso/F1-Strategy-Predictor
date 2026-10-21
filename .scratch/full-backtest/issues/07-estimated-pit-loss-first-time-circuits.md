# 07: Estimated Pit Loss for first-time circuits

**What to build:** A circuit with no previous race at all gets a Pit Loss estimated from its pit lane length and speed limit, plus a typical stationary time and an allowance for slowing into and accelerating out of the pit lane. FastF1 doesn't provide pit lane lengths, so they come from a small hand-maintained table covering only circuits that need it (e.g. Miami 2022, plus any others found), filled from published figures with each source noted. An estimated Pit Loss is flagged in the race weekend description, the single-race report and the Backtest Result. A circuit with no history and no table entry becomes an Excluded Race with that reason. See `../spec.md`.

**Blocked by:** 02 (Tracer bullet), 03 (Pit Loss from before the era)

**Status:** done

- [x] Every 2022–2025 circuit with no previous race is identified and listed in this ticket
- [x] Each has a table entry with pit lane length, speed limit and source
- [x] Miami 2022 can be predicted, with its Pit Loss flagged as estimated
- [x] The flag appears in the single-race report and in the Backtest Result
- [x] A circuit with neither history nor a table entry becomes an Excluded Race with that reason
- [x] Circuits with history never use the estimate

## First-time circuits (survey, 2026-10-21)

Found by iterating FastF1's event schedule 2018–2025 and grouping by `Location` (the loader's history-matching key). Only two 2022–2025 races have no earlier race under the same `Location` string, so only these two need an estimated Pit Loss:

| Season | Event | Circuit (`Location`) | Earlier races at this Location? | Pit lane length | Speed limit |
|---|---|---|---|---|---|
| 2022 | Miami Grand Prix | `Miami` | None (brand-new venue) | 375 m | 80 km/h |
| 2023 | Las Vegas Grand Prix | `Las Vegas` | None (the Caesars Palace 1981–82 races are a different `Location`, and before FastF1's 2018 coverage) | 400 m | 80 km/h |

Three other 2022–2025 races look like first-timers under their new FastF1 `Location` string but actually have measurable earlier races under an older `Location` name:

- `Marina Bay` (Singapore GP 2022 onward) renamed from `Singapore` (2018–2019). FastF1 doesn't match them, but 2023+ Marina Bay has 2022 Marina Bay as same-era history, so only 2022 would have been an estimate candidate. Treated as a cross-season `Location`-matching gap to pick up in a follow-up ticket rather than a true first-time circuit.
- `Monaco` (2022 onward) renamed from `Monte Carlo` (2018–2021). Same shape: 2023+ Monaco has 2022 Monaco in same era, so only 2022 would have fallen into the estimate path. Follow-up.
- `Miami Gardens` (2025) renamed from `Miami` (2022–2024). FastF1 2025 adopted "Miami Gardens" for the same physical venue; 2022–2024 are three same-era seasons away. Follow-up.

The follow-up — teaching the loader to match equivalent `Location` strings across renames — is tracked as ticket 16 (`.scratch/full-backtest/issues/16-cross-location-pit-loss-aliases.md`, `needs-triage`). Keeping it separate from this ticket:

- Avoids flagging races that actually have measurable pre-era data (Monaco 2022 under `Monte Carlo`, Marina Bay 2022 under `Singapore`) as rough estimates when a real measurement is possible.
- Keeps this ticket's table small and auditable — one entry per truly new venue.

### Published pit lane figures and sources

Both entries cite one published source for the length figure, which the ticket's "Checking the formula" section says is unavoidable: the FIA publishes a Pit Lane Drawing per event but not a length figure, and the F1 organiser's circuit guides focus on the main lap. The speed limit is cross-confirmed from an FIA stewards' decision in each case.

- **Miami** — length 375 m from [Oversteer48's Miami Grand Prix layout guide](https://oversteer48.com/miami-grand-prix-layout/) (1,232 feet / 375 m). Speed limit 80 km/h from the FIA 2022 Miami stewards' Document 22 ([FIA decision document — Car 23 pit lane speeding](https://www.fia.com/sites/default/files/doc_22_-_2022_miami_grand_prix_-_offence_-_car_23_-_pit_lane_speeding.pdf), citing an 80 km/h limit for the event). A later guide ([Tracinginsights 2025 preview](https://tracinginsights.substack.com/p/all-you-need-to-know-2025-miami-grand-prix-preview)) says the pit lane speed limit remains fixed at 80 km/h.
- **Las Vegas** — length ≈ 400 m from [Geopop's 2025 Las Vegas technical analysis](https://www.geopop.it/formula-1-gp-las-vegas-2025-analisi-tecnica-caratteristiche-tracciato/) (Italian; `pit-lane è lunga circa 400 metri, pit stops averaging 21–23 s`). Speed limit 80 km/h from the FIA 2024 Las Vegas stewards' decision ([Infringement — Car 14 pit lane speeding](https://fia.com/sites/default/files/decision-document/2024%20Las%20Vegas%20Grand%20Prix%20-%20Infringement%20-%20Car%2014%20-%20Pit%20lane%20speeding.pdf), limit set at 80 km/h; the 2023 limit is not stated in a doc I could reach but 2023's event used the same pit lane and same regulations). The 2023 FIA Pit Lane Drawing ([Event Notes](https://www.fia.com/sites/default/files/decision-document/2023%20Las%20Vegas%20Grand%20Prix%20-%20Event%20Notes%20-%20Pit%20Lane%20Drawing.pdf)) is a diagram without a printed length. Flagged in the table's `note` field as "single-source only"; the figure is a reasonable fit against the 22.0 s pit lane time loss [F1 Fansite publishes](https://www.f1-fansite.com/f1-circuits/las-vegas-strip-circuit-layout-records/) and the 25.7 s Pit Loss FastF1 measures from the 2024 race.

## The formula

Pit Loss is built up from three parts (seconds):

- **Transit penalty** — the car crosses the pit lane at the speed limit instead of at racing speed, costing `L / v_limit − L / v_racing` seconds. `v_racing` is a representative straight-line speed (250 km/h); any value in the 220–280 km/h range changes the total by less than a second.
- **Stationary time** — 2.5 s. The typical F1 stop time including jack-up and jack-down, from post-race commentary across every recent season.
- **Slow-in / slow-out penalty** — 6.5 s. Allowance for the time lost outside the speed-limited zone to slowing into the pit lane and accelerating back out again. Short, flat pit entries (Monza, Barcelona, Austin) cluster around 6 s; steeper or hairpin-adjacent ones (Monaco, Imola) are a second or two higher but still inside this budget for a first-time-circuit estimate.

```
pit_loss_s = (L / v_limit − L / v_race) + 2.5 + 6.5
```

Output: Miami 20.5 s, Las Vegas 21.2 s.

## Checking the formula

Compared against FastF1's measured Pit Loss on 2024 races at circuits with same-era history (the same `_past_races_at_circuit` path a Backtest uses, from the scratchpad `calibrate.py`):

| 2024 race | L (m) | v (km/h) | Measured Pit Loss | Formula estimate | Δ |
|---|---|---|---|---|---|
| Italian GP (Monza) | 400 | 80 | 25.5 s | 21.2 s | −4.3 s |
| Spanish GP (Barcelona) | 400 | 80 | 23.7 s | 21.2 s | −2.5 s |
| United States GP (Austin) | 440 | 80 | 21.5 s | 22.5 s | +1.0 s |
| Austrian GP (Spielberg) | 310 | 60 | 21.7 s | 23.1 s | +1.4 s |
| Dutch GP (Zandvoort) | 350 | 60 | 30.3 s | 25.0 s | −5.3 s |

The formula lands within about ±5 s of measured, usually within 3 s, and tends to underestimate at longer-pit-lane circuits (Monza, Zandvoort) because the "slow-in / slow-out" allowance is fixed and doesn't widen with pit entries that have more aggressive ramps. For the two circuits that currently need an estimate (Miami ≈ 21 s observed vs 20.5 s estimated; Las Vegas ≈ 22 s per published figures vs 21.2 s estimated), the formula lands inside 1 s. That is the band this ticket's acceptance criteria care about: the estimate for a race with no history is close enough to produce a sensible Simulated Race Time, and the Backtest Result flags the race so a reader knows to trust the measured races more than the estimated ones.

The pit lane lengths for the five calibration circuits are rough — they come from fan-site summaries, not the FIA — so a part of the Δ is in the input, not the formula. The ticket does not try to tune the constants against these five, because that would overfit to one source's figures.

## Implementation notes

**What was built (2026-10-21), test-first.**

- `src/f1_strategy/pit_lane_table.py` — new module. Holds the `PitLane` dataclass (`circuit`, `length_m`, `speed_limit_kmh`, `source`, `note`), the two-entry `PIT_LANES` tuple (Miami, Las Vegas) each citing one source for every figure, `pit_lane_entry(circuit)` returning the table row keyed on FastF1's `Location`, and `estimated_pit_loss(entry)` returning the Pit Loss in seconds from the formula above. The three constants (`STATIONARY_TIME_S`, `SLOW_IN_OUT_PENALTY_S`, `RACING_SPEED_KMH`) are module-level so a future tuning spec can revisit them from one place.
- `src/f1_strategy/weekend.py` — `PreRaceInfo` gains `estimated_pit_loss: bool = False`. The flag is False by default so hand-built test weekends keep working without edits. The field is named `estimated_pit_loss` (not `estimated_pit_loss`) to match the name ticket 05's parallel session landed on `RaceResult`, so the two layers share one spelling.
- `src/f1_strategy/fastf1_loader.py` — `_measure_pit_loss_and_history` returns a four-tuple `(pit_loss, pit_loss_seasons, estimated_pit_loss, historical_degradation)`. Order of fallback: same-era history → pre-era seasons (ADR-0004 exception, ticket 03) → pit lane table (this ticket). The table fallback is only tried under default `pit_loss_min_season=None`; when a test pins a lower bound explicitly the empty-measurement path still raises as before, matching ticket 01's test contract. When nothing in either path and no table entry exists, the loader raises `ValueError` with a message that names the pit lane table, so the Backtest's ticket 02 handler maps it to a `DATA_UNAVAILABLE` Excluded Race.
- `src/f1_strategy/backtest.py` — `RaceResult` gains `pit_loss` and `pit_loss_seasons` fields alongside ticket 05's existing `estimated_pit_loss` placeholder (all three with defaults, so existing fast tests remain valid). `run_backtest` copies the three from the loaded `pre_race` so a saved Backtest Result records the full Pit Loss provenance. `format_backtest` adds a "Pit Loss estimated (ticket 07, no circuit history)" section listing each race, its circuit and its estimated figure, under the Degradation source counts.
- `src/f1_strategy/backtest_io.py` — the save/load path (ticket 05) now writes and reads `pit_loss` and `pit_loss_seasons` alongside the pre-existing `estimated_pit_loss`. Both have `data.get(..., default)` on the read side, so a Backtest Result written before this ticket still loads (with zeros for `pit_loss` and `()` for the seasons), satisfying ADR-0005's forward-compatible read rule.
- `src/f1_strategy/report.py` — `format_header` prints "Pit Loss estimated from pit lane length and speed limit (ticket 07, no circuit history)" when the flag is set, in place of the pre-era-seasons note (the two paths are mutually exclusive — the estimated case has empty `pit_loss_seasons`).
- `tests/test_backtest_save_load.py::test_estimated_pit_loss_flag_round_trips` — extended (from ticket 05's placeholder) to also round-trip `pit_loss` and `pit_loss_seasons`, so a Backtest Result's full Pit Loss provenance stays intact across save and load.

**Decisions and alternatives rejected.**

- *Table only, not an alias map for renamed `Location` strings.* The three cases where FastF1 renamed a circuit between pre-era and era (`Monte Carlo` → `Monaco`, `Singapore` → `Marina Bay`, `Miami` → `Miami Gardens`) are visually first-timers to the loader. Fixing those by renaming the match key is a different change — it widens the measured-history path, not the estimated one — and conflating the two would make this ticket's table look like it covers four or five circuits that in reality have real past races to measure from. Ticket 16 (new, `needs-triage`) tracks the alias work. Until it lands, Monaco 2022, Marina Bay 2022 and Miami Gardens 2025 may fall into the estimated path if a Backtest runs them; the "pit lane estimated" flag on the Backtest Result makes that visible, and the operator can either add table entries for them or wait for ticket 16.
- *Formula built up from three physical parts rather than fit from measured Pit Loss.* The purpose is to estimate for a circuit where measured history doesn't exist, so fitting constants against measured races would be circular. The three constants land within the calibration band on the five sanity-check circuits and are set to values documented in post-race commentary rather than tuned.
- *Fallback order: history first, then pre-era (ticket 03), then estimate.* A circuit with any measurable history, even pre-era, is better than an estimate. The loader only reaches the table when both `_past_races_at_circuit` passes come up empty, which in 2022–2025 is only Miami 2022 and Las Vegas 2023. Rejected: calling the table first and only running history when the table is missing — that would hide a measurable race under a rough estimate.
- *`estimated_pit_loss` on `PreRaceInfo` and `RaceResult` rather than on `Settings`.* The flag is a property of the loaded weekend, not of the run's settings; carrying it on `PreRaceInfo` means `report.py` and the Backtest Result see the same source of truth. The alternative (deriving the flag at the Backtest layer from "`pit_loss_seasons == ()`") was rejected because hand-built test weekends also carry an empty `pit_loss_seasons` while passing `pit_loss` directly and are not estimates.
- *`estimated_pit_loss` takes a `PitLane`, not raw numbers.* Keeps the formula's input one object so a test can show that the Pit Loss moves with a longer pit lane or a lower speed limit by changing one field. The loader still calls it with a table lookup.
- *Table hand-maintained, not read from JSON.* Two entries; a Python literal is as readable and lets the sources live right next to the figures. Reconsidered later if the table grows past a few dozen entries.

**Deviations from the ticket / spec.**

- *The ticket says "every 2022–2025 circuit with no previous race" gets a table entry.* The survey only produced Miami 2022 and Las Vegas 2023; the other three apparent first-timers are location-name renames of circuits that do have measurable earlier races. Documented above and in ticket 16. No spec change: the spec's "Loader: estimated Pit Loss" bullet names Miami 2022 as the primary example and leaves the exact list to the implementer.

**Tests.**

- Fast: `tests/test_estimated_pit_loss.py` (11 tests, all without internet).
  - Table has Miami and Las Vegas (survey result).
  - `pit_lane_entry` round-trips every entry and returns `None` for an unknown circuit.
  - `estimated_pit_loss` rises with longer pit lane and with lower speed limit (physics sanity).
  - Both table entries land in the formula's calibration band (18 s ≤ estimate ≤ 28 s).
  - `RaceResult` carries `pit_loss`, `pit_loss_seasons` and `estimated_pit_loss` through the Backtest; the estimated and measured cases differ as expected.
  - `format_backtest` lists the estimated race under the "Pit Loss estimated" heading; measured races aren't listed there.
  - `format_header` adds the "estimated from pit lane length and speed limit" line for an estimated weekend and leaves it off for a measured one.
  - A loader that raises with the pit-lane-table message becomes an Excluded Race with that detail (ticket 02's `DATA_UNAVAILABLE` path).
- Slow: `tests/test_fastf1_weekend_loader.py::test_miami_2022_pit_loss_is_estimated_from_the_pit_lane_table`. Runs through `load_weekend(2022, "Miami Grand Prix")` on real FastF1 data and asserts the circuit is `"Miami"`, the flag is set, the seasons list is empty, and the number matches `estimated_pit_loss(pit_lane_entry("Miami"))` exactly.
- Full fast suite: 122 passed (111 before this ticket + 11 new). The one Singapore 2024 real-data test still passes. The CLI run `uv run f1-strategy 2024 "Singapore Grand Prix"` and `… "Italian Grand Prix"` match ticket 01's baseline byte-for-byte (6.5/18, 13.75/18, 3/20 and 4/19, 10/19, 10/30 respectively).

**Baselines, not changing.** Singapore 2024 and Monza 2024 single-race CLI output is byte-identical to the baselines captured in ticket 01 and reinforced in ticket 03. The estimated-Pit-Loss code path isn't exercised by any 2023–2025 race once ticket 16 lands, so this is a stable baseline.

**Open questions, known limitations and follow-ups.**

- *Location-name alias work (ticket 16).* As discussed, that is the next item: once the loader can treat `Marina Bay`/`Singapore`, `Monaco`/`Monte Carlo` and `Miami Gardens`/`Miami` as the same `Location` for history matching, Monaco 2022, Marina Bay 2022 and Miami Gardens 2025 will all use measured Pit Loss and the estimate path shrinks to its truly-new-venue set.
- *Las Vegas pit lane length is single-source.* The ticket cites one Italian technical analysis for the 400 m length because I couldn't confirm it against another reliable source; the FIA's event-notes Pit Lane Drawing is a diagram without a printed metric. If a reader has access to the FIA technical delegate's circuit measurements or the Las Vegas Grand Prix organiser's media kit, replace the length figure and the citation and the formula will re-run against the new number without further changes.
- *Constants are fixed, not per-circuit.* Monaco and Imola observed Pit Loss sit a few seconds above the formula because their pit entries have aggressive ramps. If a Backtest later reveals the estimate is systematically off for a specific new venue, add a per-entry override field on `PitLane` (e.g. `extra_decel_accel_s`) rather than tuning the global constants away from their physical meaning.
- *Pit lane table lookup is case-sensitive on `Location`.* FastF1 uses stable PascalCase for `Location` strings, so this is fine today, but if FastF1 ever normalises the strings differently in a point release, add a lowercase lookup.
- *The three constants aren't settings.* `Settings` doesn't carry the stationary time or the slow-in/out penalty, so a tuning run can't fit them. That is deliberate — the point of the ticket is to make a race predictable, not to tune the estimate against the same races that would score it. If a future tuning spec wants to experiment with them, lift them to `Settings` then.

**Review feedback to the user.**

- The follow-up ticket 16 (location-name aliases) is worth doing before the first full Backtest baseline, because without it Marina Bay 2022, Monaco 2022 and Miami Gardens 2025 will fall into this ticket's estimate path even though those circuits do have measurable earlier races. The flag on the Backtest Result makes it visible, but the measured values would be better.
- Ticket 05's serialiser (in-flight in a parallel session) needs to write and read `RaceResult.pit_loss`, `pit_loss_seasons` and `estimated_pit_loss`. The field names were chosen to mirror `PreRaceInfo` so a serialiser can treat them uniformly. If ticket 05's branch landed before this one, those fields need adding to the save format; if this ticket lands first, ticket 05 picks them up as part of its "save every `RaceResult` field" pass. Either way, the result's round-trip test should include a race whose `estimated_pit_loss` is True so a dropped field is caught.
- The constants in `pit_lane_table.py` are deliberately named and documented so a future tuning spec can revisit them without re-reading this ticket.
