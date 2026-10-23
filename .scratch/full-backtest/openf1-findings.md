# OpenF1 as a second data source for the race weekend description

**Ticket:** [18 – Check OpenF1 as a second data source](issues/18-check-openf1-as-second-data-source.md)
**Date:** 2026-10-23
**Author:** Research session (Claude Opus 4.7)

## TL;DR

Yes, [OpenF1](https://openf1.org/) can supply every field in the race weekend description for 2023–2025, with two small derivations (per-lap tyre age, per-lap neutralisation flag) and one small compromise (no persistent Tyre Set id, same as FastF1 today). It covers 2023 onward only, so 2022 and pre-era races still need FastF1. Building a second loader is worth it: it unblocks the full 2023–2025 Backtest without an F1 TV subscription and sits cleanly behind the existing `fastf1_loader` seam. Recommendation: **build it**, in roughly six tickets (see below). An ADR is recommended to pin the per-season data-source policy.

## Why this ticket exists

Since ~15 Oct 2026, F1's live-timing archive (`livetiming.formula1.com/static`) returns HTTP 401 to unauthenticated clients; FastF1's mirror only serves 2021 and 2022, so on a cold cache every 2023+ (and every 2018–2020 pre-era history) race fails with `DataNotLoadedError`. The second baseline Backtest attempt (2026-10-23) scored 15 of 92 races for this reason (see [ticket 09 Comments](issues/09-first-full-backtest-baseline.md)). FastF1's maintainer has shipped a `3.9.0a0` alpha that adds F1 TV authentication (see "FastF1 issue #978" below), but that needs a paid F1 TV Access subscription — out of scope here. OpenF1 is the one unauthenticated path left for 2023+.

## OpenF1 coverage, terms, limits (sources)

| Property | Value | Source |
|---|---|---|
| Historical season coverage | 2023, 2024, 2025 | Probed `GET /v1/meetings?year=<yyyy>` for 2018–2025; 2018–2022 return 0 rows, 2023–2025 return 24/25/25. Confirmed on landing page: "Access to all 18 endpoints and historical sessions since 2023" ([openf1.org JSON-LD](https://openf1.org/)) |
| Free-tier rate limit | 3 req/s and 30 req/min | [openf1.org FAQ](https://openf1.org/): "The free tier allows 3 req/s and 30 req/min…" |
| Supporter tier | 6 req/s, 60 req/min, 10 MQTT/WebSocket, €9.90 | Same FAQ, and the `SoftwareApplication` schema's offer: `"name":"Historical and Live data","price":"9.90"` |
| Live-data gate | Data from a session still in progress or ended < 30 min ago is paid-only; everything older is free | Same FAQ |
| Authentication for historical data | None required | Confirmed: every request in this document was anonymous `curl` and returned 200 with data |
| Licence | **CC BY-NC-SA 4.0** — non-commercial, share-alike, attribution encouraged (not required) | [`openf1.org`](https://openf1.org/) JSON-LD: `"license":"https://creativecommons.org/licenses/by-nc-sa/4.0/"`; the FAQ says credits are appreciated but not required |
| Officialness | **Independent, community-driven**, not associated with F1/FIA/FOM | FAQ: "Is OpenF1 official? No." |
| Intended use | "Educational purposes, personal learning projects, research, and non-commercial fan engagement" | FAQ |
| Response time | ~0.6 s for a session-list query from this machine | `curl -w "time_total"` on `/v1/sessions?year=2024&session_type=Race&country_name=Belgium`: 0.62 s |

**Licensing implication for this project.** NC-SA 4.0 is compatible with a personal/educational predictor like this one, but it would preclude distributing predictions commercially without a separate licence from OpenF1. Record that in the ADR, don't act on it beyond adding a note to README.

## FastF1 issue #978 status (as of 2026-10-23)

- **State:** open, 5 comments, last updated 2026-10-19 ([Fast-F1#978](https://github.com/theOehrly/Fast-F1/issues/978)).
- **Root cause confirmed:** F1 enabled authentication on `livetiming.formula1.com/static` around 14–15 Oct 2026 (CloudFront 401). Affects every season, 2021 included — the "mirror serves 2021–2022" is FastF1's own mirror, not F1's archive.
- **Workaround (official):** maintainer `theOehrly` shipped **`fastf1==3.9.0a0`** on 2026-10-18 which supports F1 TV authentication. Needs an **F1 TV Access subscription**. Out of scope for ticket 18 per the brief ("Paid or authenticated data sources (e.g. F1 TV tokens)").
- **Implication for us:** the FastF1 path for 2023+ now has a known fix behind a paywall. If the user ever buys F1 TV, FastF1 remains the single source of truth and ticket 18's second loader becomes optional. For now, OpenF1 is the only free fix.

## Weekends sampled

Every claim in the table below is backed by a real request against `https://api.openf1.org/v1/` on 2026-10-23. The three weekend types the ticket requires:

| Role | Weekend | Meeting key | Race session key | Why |
|---|---|---|---|---|
| Conventional, no neutralisation | Italian GP (Monza), 2024-09-01 | 1244 | 9590 | Clean conventional-format weekend, 0 SC/VSC — exercises the FP1/FP2/FP3/Q/R path and the baseline Pit Loss / per-lap derivations |
| Sprint | Austrian GP (Spielberg), 2024-06-30 | 1239 | 9550 (Race), 9549 (Sprint) | Sprint-format weekend; exercises FP1/SQ/Sprint/Q/R session set and used-tyre starting age (Sprint stint 1 for VER starts at `tyre_age_at_start=5`) |
| Neutralised | São Paulo GP (Interlagos), 2024-11-03 | 1249 | 9636 | VSC on lap 28, SC on lap 30, red flag on lap 32, SC again on laps 39–42; exercises the race_control → neutralisation period derivation and the "pit_duration polluted by red flag" edge case |

Austrian GP race itself also contains a short VSC (lap 66, VER–NOR crash), which doubles as a second neutralisation spot-check inside the sprint sample.

## Field-by-field table

Legend for the "Via OpenF1" column: ✅ = direct field; ⚙️ = derived (recipe in notes); ❌ = missing.

### Event schedule

| Field (loader today) | FastF1 source today | OpenF1 endpoint / field | Direct? | Notes & evidence |
|---|---|---|---|---|
| Location (circuit) | `event.Location` (string) | `GET /v1/meetings?year=Y` → `meetings[].location` | ✅ | Monza 2024: `"location":"Monza"`; Austria: `"Spielberg"`; São Paulo: `"São Paulo"`. Matches FastF1's `Location` strings for the three samples. Loader's existing `location_aliases` ticket 16 may still be needed if OpenF1 and FastF1 ever disagree on a venue's name (not seen in the three samples) |
| Round number | `event.RoundNumber` | — | ⚙️ | Not present on `/v1/meetings`. Derive by sorting the year's non-testing meetings by `date_start` and numbering from 1. The 2024 listing came back already in chronological order with "Pre-Season Testing" (`meeting_name` lacks "Grand Prix") as the only non-round entry |
| Sprint vs conventional (`EventFormat`) | `event.EventFormat` ("conventional" / "sprint_*") | — | ⚙️ | Not an explicit field. Derive from `GET /v1/sessions?meeting_key=M`: a sprint weekend has `session_name` values `{"Practice 1", "Sprint Qualifying", "Sprint", "Qualifying", "Race"}`; a conventional weekend has `{"Practice 1", "Practice 2", "Practice 3", "Qualifying", "Race"}`. Monza returned the five conventional names; Austria and São Paulo returned the five sprint names |
| Sessions list (FP1–FP3, SQ/Sprint, Q, R) | `event.SessionN` strings | `GET /v1/sessions?meeting_key=M` → `sessions[].session_name` | ✅ | `session_name` values seen match the five-element sets above |

### Per-driver per-lap (every pre-race session + race)

| Field | FastF1 source today | OpenF1 endpoint / field | Direct? | Notes & evidence |
|---|---|---|---|---|
| `driver` (TLA) | `laps.Driver` + `results.Abbreviation` | `GET /v1/drivers?session_key=S` → `drivers[].name_acronym`, joined on `driver_number` | ⚙️ | OpenF1 lap rows carry `driver_number` only (integer); map to TLA via `/v1/drivers`. Monza race `drivers` returned 20 rows with TLAs matching the FastF1 roster (`VER`, `LEC`, `NOR`, …) |
| `lap_number` | `laps.LapNumber` | `/v1/laps` → `lap_number` | ✅ | Integer, consistent with FastF1 |
| `lap_time` (seconds) | `laps.LapTime` (Timedelta) | `/v1/laps` → `lap_duration` (seconds, float) | ✅ | Monza lap 5 for #1 returned `"lap_duration": 85.218`. Can be `null` for in-progress or invalidated laps (observed `null` for Monza FP1 lap 5 for #1, a slow out-lap). Current loader already skips laps where lap time is missing |
| `tyre_set` (per-stint id) | Loader builds `"{driver}-{session}-stint{N}-{compound}"` from FastF1 columns | Same recipe, using `/v1/stints` fields (`driver_number`, `stint_number`, `compound`) | ⚙️ | OpenF1 has no persistent Tyre Set id either, so parity with the current loader is exact. [ADR-0002](../../docs/adr/0002-remaining-sets-count-new-only.md) already documents that we don't track Tyre Set identity across sessions |
| `compound` | `laps.Compound` | `/v1/stints` → `compound`, mapped per-lap via `lap_start`…`lap_end` | ⚙️ | OpenF1 attaches compound to the stint, not the lap. Join: for each lap, pick the stint where `lap_start ≤ lap_number ≤ lap_end`. Compound values are uppercase (`"HARD"`, `"MEDIUM"`, `"SOFT"`, `"INTERMEDIATE"`, `"WET"`) — same spelling the loader already maps via `_COMPOUND` |
| `tyre_age` (laps on set at this lap) | `laps.TyreLife` | — | ⚙️ | Derived: `tyre_age = (lap_number - stint.lap_start) + 1 + stint.tyre_age_at_start`. `/v1/stints` carries `tyre_age_at_start` per stint (observed: Austria R VER stint 3 `MEDIUM` with `tyre_age_at_start=3`, i.e. a used set) |
| `new_when_fitted` | `laps.FreshTyre` | — | ⚙️ | Derived: `new_when_fitted = (stint.tyre_age_at_start == 0)`. In the three samples, every stint whose `tyre_age_at_start == 0` corresponds to a new set the team was known to have fitted; used sets show `tyre_age_at_start ≥ 1` (Austria R VER MEDIUM stint 3: 3; Monza FP1 VER re-stint on same soft: 5 and 8). Loader can keep its boolean |
| `pit_in` | `laps.PitInTime.notna()` | `/v1/pit` → `lap_number` set per driver | ⚙️ | Pit stops come as events, not lap flags. Derive: `pit_in = lap_number ∈ {r.lap_number for r in pit_rows}`. Monza R returned 30 pit rows across 19 drivers (VER=2, LEC=1, STR=3 — matches public records) |
| `pit_out` | `laps.PitOutTime.notna()` | `/v1/laps` → `is_pit_out_lap` | ✅ | Direct boolean on the lap row |
| `neutralised` (lap under SC/VSC) | `laps.TrackStatus` codes | `/v1/race_control` + lap-range reconstruction | ⚙️ | OpenF1 has no per-lap TrackStatus. Reconstruct lap ranges from race_control events (next row) and set `neutralised = lap_number ∈ any period` |

### Pit lane timing

| Field | FastF1 source today | OpenF1 endpoint / field | Direct? | Notes & evidence |
|---|---|---|---|---|
| Pit stop lap + in/out flags | Derived from `PitInTime`/`PitOutTime` | `/v1/pit` → `lap_number`; `/v1/laps.is_pit_out_lap` | ⚙️ | See above |
| Per-stop lane time | — (not directly used by loader) | `/v1/pit` → `pit_duration` (= `lane_duration`) | ✅ with caveat | Non-null in all 30 Monza R rows, all 45 Austria R rows, all 35 São Paulo R rows. **Caveat:** at São Paulo the mean `pit_duration` was 661 s because the red-flag stationary time was counted as a "pit stop". OpenF1's `pit_duration` therefore cannot be used as-is for Pit Loss on neutralised races. The current loader never uses this field — it computes Pit Loss from in-lap + out-lap deltas against the driver's green-flag median — and that algorithm ports to OpenF1 unchanged |
| Per-stop stationary time | — | `/v1/pit` → `stop_duration` | ❌ | Null for all 30 Monza rows, all 45 Austria rows, and 23/35 São Paulo rows. Not usable |

The loader's existing [`_pit_losses_in`](../../src/f1_strategy/fastf1_loader.py) uses `(in_lap_time − reference) + (out_lap_time − reference)` with a filter on `TrackStatus == "1"`. Ported to OpenF1 it becomes: same arithmetic, but "green flag" is checked via the reconstructed neutralisation ranges and `lap_duration` replaces `LapTime`. Same clip (`10 < loss < 60 s`) applies.

### Race

| Field | FastF1 source today | OpenF1 endpoint / field | Direct? | Notes & evidence |
|---|---|---|---|---|
| Stints (`driver, compound, start_lap, end_lap`) | Grouped from race `laps.Stint` | `/v1/stints?session_key=<race>` | ✅ | Fields map 1:1: `driver_number`, `compound`, `lap_start`, `lap_end`. Monza R for #1 returned three stints (H 1–22, H 23–41, M 42–53) — matches public records |
| SC / VSC periods (`kind, start_lap, end_lap`) | Scanned from leader-lap `TrackStatus` | `/v1/race_control?session_key=<race>` | ⚙️ | Events carry `category`, `message` and `lap_number`. Rules observed in samples: `category == "SafetyCar"` with `message` containing `"VIRTUAL SAFETY CAR DEPLOYED"` → VSC starts on that `lap_number`; `"VIRTUAL SAFETY CAR ENDING"` → ends same `lap_number`; `"SAFETY CAR DEPLOYED"` → SC starts; `"SAFETY CAR IN THIS LAP"` → SC ends same `lap_number`. Red flag (`flag == "RED"`) is not a neutralisation in the loader today (`_lap_neutralisation_kind` ignores it) — same here. São Paulo R produced the expected sequence (VSC lap 28; SC laps 30–?; red flag lap 32; SC laps 39–42); Austria R produced VSC on lap 66; Monza R produced none |
| Per-starter team | `results.TeamName` for drivers with `GridPosition > 0` | `/v1/drivers?session_key=<race>` → `team_name`; starter set from `/v1/starting_grid?session_key=<quali>` | ⚙️ | Monza drivers returned 20 rows with sensible team names (`Red Bull Racing`, `McLaren`, `Ferrari`, …, `Kick Sauber`, `RB`). Starter list from `starting_grid?session_key=9586` returned 20 rows covering positions 1–20. **Note:** `/v1/starting_grid` is attached to the **qualifying** session, not the race (`?session_key=9590` returned `"No results found."`). The loader port needs to resolve the quali key from the meeting |
| Finishing status (took the flag?) | `results.Status == "Finished" or "Lapped" or "+N Lap"` | `/v1/session_result?session_key=<race>` | ✅ | Returns one row per driver with explicit `dnf`, `dns`, `dsq` booleans and `gap_to_leader` as either seconds or `"+1 LAP"`. Finishing status is `not dnf and not dns and not dsq`. Monza returned 1 DNF (Tsunoda); São Paulo returned 2 DNF (Sainz, Colapinto), 2 DNS (Albon, Stroll), 1 DSQ (Hülkenberg) — all matching the official classification |
| Race total laps | `race.total_laps` | `/v1/session_result?session_key=<race>` → winner's `number_of_laps` | ⚙️ | Monza winner `number_of_laps=53`; Austria winner `71`; São Paulo winner `69`. Max over the result set gives the race lap count |

### Not needed by the loader today (but relevant)

- **Historical Degradation** is read from past races' race laps + stints, i.e. the same OpenF1 endpoints as above. For 2023+ races it's covered; for 2022 first-season races it's drawn from 2022 only, which still needs FastF1.
- **Weather / telemetry / car data**: loader doesn't use them (`race.load(laps=True, telemetry=False, weather=False, messages=False)`). OpenF1 has `/v1/weather`, `/v1/car_data`, `/v1/location` if later tickets want them.
- **Tyre Allocation**: FastF1 doesn't expose it either; the loader defaults from the weekend format per [ADR-0002](../../docs/adr/0002-remaining-sets-count-new-only.md). OpenF1 doesn't expose it either. **No regression.**

## Does it still give one consistent weekend description?

Yes, with a per-season routing rule:

- **2023, 2024, 2025:** use OpenF1 (free, works today).
- **2022 (first season of the current era):** keep FastF1 — its mirror still serves 2022, and the current baseline includes it.
- **2018–2020 (pre-era Pit Loss fallback for 2022 first-time circuits):** FastF1 can't serve these today without F1 TV auth, and OpenF1 doesn't cover them at all. This is already a known hole (ticket 09, second attempt comment), and the loader's existing pit-lane-table fallback ([ticket 07](issues/07-estimated-pit-loss-first-time-circuits.md)) covers Miami 2022 and Las Vegas 2023; the remaining 2022 Australia/Canada/Belgium/Singapore/Japan gap is the one place this plan doesn't fix. Flag in ADR.

The weekend description shape (`PreRaceInfo`, `RaceOutcome`, `Lap`, `Stint`, `NeutralisationPeriod`) is identical across sources — the choice of loader is below the `RaceWeekend` seam and callers can't tell. The only visible difference is `tyre_set` ids, which already differ across sessions today and are only used for same-stint uniqueness.

## Known data-quality notes

- **`pit_duration` conflates red-flag parking with a pit stop** at São Paulo R (mean 661 s). Don't use it for Pit Loss; keep the current lap-time-based algorithm.
- **`stop_duration` is null** in effectively every row inspected (0/30 non-null at Monza, 0/45 at Austria, 12/35 at São Paulo). Treat as unavailable.
- **`lap_duration` can be null** for pit-in laps and in-progress laps in practice. Loader already handles this by skipping (`fastf1_loader._laps_from`).
- **Round number and sprint-vs-conventional** are not stored directly on `/v1/meetings`. Derivation is simple but has to be ported.
- **Starting grid lives on the quali session**, not the race session. Resolution step needed.
- **Team naming** matched FastF1 in the three samples; a small alias table may still be prudent (same shape as `location_aliases.py`).
- **No per-lap TrackStatus**. The race_control reconstruction needs the "ENDING" messages for VSC and "IN THIS LAP" for SC; a race whose feed is missing an "end" event could leak a period to the end of the race. Add a safety ceiling (end at race lap count) and log any such case as a quality warning.
- **Rate limit is 30 req/min** on free tier. A race weekend fetch is ~10 requests (meetings, sessions, drivers, starting_grid, 5× (laps, stints), race_control, pit, session_result), so one weekend ≈ 20 s of throughput budget. A full 24-race season ≈ 8 min of requests, well within reach. The loader's existing [`rate_limit.py`](../../src/f1_strategy/rate_limit.py) can be reused as-is with a different cap. **No block.**

## Recommendation

**Build a second loader.** The whole weekend description is reachable through OpenF1 with modest derivation, 2023–2025 coverage lines up exactly with the gap FastF1 opened in Oct 2026, the free tier is enough, and no paid F1 TV subscription is pulled into the project's hard dependencies. The alternative — waiting for FastF1 3.9 stable or asking the user to pay for F1 TV — is reasonable too but keeps the project blocked and tied to one supplier.

The second loader goes behind the same `load_weekend` / `list_season` surface as `fastf1_loader.py`, selected per season. 2022 and pre-era history keep FastF1. 2023–2025 use OpenF1.

### Rough ticket breakdown

Suggested as six new tickets in `.scratch/full-backtest/issues/` with `Status: needs-triage`:

1. **ADR-0006: per-season data source policy.** Record: FastF1 for 2018–2022, OpenF1 for 2023+, OpenF1's CC BY-NC-SA 4.0 licence (non-commercial), the 2018–2020 pre-era Pit Loss hole, and that the loader seam makes the choice invisible to callers. Also note the FastF1 3.9 F1 TV path as a reversible future option.
2. **OpenF1 client + rate limiter.** Thin HTTP client with the free-tier limit (3 req/s, 30 req/min), on-disk cache keyed by request URL (JSON responses), and the usual retry/backoff. Reuses `rate_limit.py`.
3. **OpenF1 weekend loader (pre-race).** `openf1_loader.load_weekend` building `PreRaceInfo` + `Session`/`Lap`: schedule derivation (round, format, sessions), driver roster (TLA/team), per-session laps joined with stints to attach compound/tyre_age/new_when_fitted. Tests against hand-fixtured responses for Monza FP1 and Austria Sprint.
4. **OpenF1 race loader (RaceOutcome + Pit Loss).** `_race_stints` from `/v1/stints`, `_neutralisation_periods` from `/v1/race_control` (with the end-of-race safety ceiling), `_finishing_status` from `/v1/session_result`, and `_pit_losses_in` re-written to work on OpenF1 lap+race_control+pit rows. Tests against the three sampled weekends.
5. **Season router + `list_season` port.** `data.load_weekend(season, event)` dispatches to `openf1_loader` for season ≥ 2023 and to `fastf1_loader` otherwise. `list_season` dispatches the same way, deriving round/format for OpenF1. One integration test per branch.
6. **Re-run the full 2022–2025 baseline Backtest** (upgrades of [ticket 09](issues/09-first-full-backtest-baseline.md)): confirm Singapore 2024 matches its known scores via the OpenF1 path, write the new baseline into `results/backtest/`, and compare against the FastF1-era baseline for 2022.

Not blocked by this ticket: ticket 17 (FastF1 rate-limit wait) already landed and the OpenF1 loader can borrow its wait helper, keeping the architecture of ticket 06 (`BacktestResult` compare) untouched.

## Appendix: requests used

Every request below was run anonymously with `curl` from this session on 2026-10-23 and returned HTTP 200 unless noted.

- Reachability check: `GET /v1/sessions?year=2024&session_type=Race&country_name=Belgium` → HTTP 200, 0.62 s
- Season probe (coverage): `GET /v1/meetings?year={2018..2025}` → 0, 0, 0, 0, 0, 24, 25, 25 rows
- Weekend lists: `GET /v1/meetings?year=2024&country_name=Italy|Austria|Brazil`
- Sessions per meeting: `GET /v1/sessions?meeting_key=1244|1239|1249|1248`
- Laps: `GET /v1/laps?session_key=9590&driver_number=1&lap_number=5`, `/v1/laps?session_key=9583&driver_number=1&lap_number=5`
- Stints: `GET /v1/stints?session_key=9590|9583|9549|9550&driver_number=1`
- Pit: `GET /v1/pit?session_key=9590|9550|9636` (+ per-driver variant for #1 at Monza)
- Race control: `GET /v1/race_control?session_key=9590|9550|9636|9625`
- Drivers: `GET /v1/drivers?session_key=9590`
- Starting grid: `GET /v1/starting_grid?session_key=9590` (404-ish body) and `?session_key=9586` (20 rows)
- Session result: `GET /v1/session_result?session_key=9590|9636`
- Position: `GET /v1/position?session_key=9590&position<=5`
- Landing page for terms and rate limits: `GET https://openf1.org/`
- FastF1 issue 978 state: `GET https://api.github.com/repos/theOehrly/Fast-F1/issues/978` and `/comments?per_page=100`

Raw command transcripts are in the session log; findings above are the only persisted record.
