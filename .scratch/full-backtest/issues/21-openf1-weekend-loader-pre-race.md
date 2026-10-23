# 21: OpenF1 pre-race weekend loader

**What to build:** `src/f1_strategy/openf1_loader.load_weekend` that builds `PreRaceInfo` + the `Session`/`Lap` tuples for every pre-race session (FP1–FP3 or FP1+Sprint+SQ, plus Q) for a 2023+ race weekend. Mirrors the shape of `fastf1_loader.load_weekend` so the two sit behind one seam. Derivations required (recipes verified against real responses in the findings):
- Round number from meeting date order.
- Sprint vs conventional from the session set.
- Driver TLA from `/v1/drivers.name_acronym`.
- Compound/tyre_age/new_when_fitted per lap from `/v1/stints` joined onto `/v1/laps`.
- `pit_in` per lap from `/v1/pit.lap_number`; `pit_out` from `/v1/laps.is_pit_out_lap`.

**Blocked by:** 20 (client).

**Status:** needs-triage

**Category:** enhancement

Field-by-field recipes and sample responses in [`openf1-findings.md`](../openf1-findings.md). Follow-up from [ticket 18](18-check-openf1-as-second-data-source.md).

**Out of scope:** the race session, pit loss and historical degradation — ticket 22.
