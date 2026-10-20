# 11: No Degradation estimate when nobody runs a Compound in practice

**What to build:** Predict a race even when no team produced a Long Run or Push Laps on one dry Compound. Today `predict()` raises "No Long Runs or Push Laps on Hard across the field" (ticket 02's deliberate choice not to invent a rate). It's common: teams often save the Hard for the race.

**Blocked by:** None

**Status:** needs-triage

- [ ] A weekend where no team ran one dry Compound still gets Strategy Predictions
- [ ] The Degradation source for that Compound says it was not measured this weekend
- [ ] Monza 2024 can be predicted
- [ ] The command reports the gap clearly instead of a traceback if prediction is still refused

## Comments

**From ticket 08 (2026-10-20).** Of 7 recent conventional 2024 races screened, 3 are refused for this reason: Monza, Abu Dhabi and Las Vegas, all on the Hard. At Monza only Tsunoda ran Hards (three FP1 Stints: one Push Lap per set, or a 3-lap run below the 4-lap Long Run minimum), and the five FP3 Hard laps are all in-laps. Yet all 20 starters raced the Hard.

Options to weigh, all modelling decisions that likely need an ADR because they reverse ticket 02:
- Borrow the next-softer Compound's field-average Degradation as an upper bound (harder Compounds rarely wear faster), with a new Degradation source.
- Use the circuit's Degradation from previous seasons' races (needs a history store; fits with Circuit Tendency).
- Fit from shorter runs only for Compounds that would otherwise have nothing (lower `min_long_run_length` per Compound).
