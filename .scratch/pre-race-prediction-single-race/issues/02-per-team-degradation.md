# 02: Per-team Degradation with fuel correction

**What to build:** Replace the field-wide Degradation with Degradation fitted per Compound per team from fuel-corrected Long Run laps, falling back to the field average when a team has no Long Runs on a Compound. Each Degradation estimate reports where it came from. Teams that wear their tyres harder now get different favourite Strategies from teams that don't. The fuel effect per lap is a setting with a sensible default.

**Blocked by:** 01 (Tracer bullet)

**Status:** ready-for-agent

- [ ] Degradation is estimated per team per Compound from Long Runs
- [ ] Long Run lap times are corrected for fuel burn before fitting, so a Long Run that gets faster from fuel alone shows no false improvement
- [ ] A team with no Long Runs on a Compound uses the field average for it
- [ ] Predictions expose each team's Degradation source per Compound (Long Runs or field average)
- [ ] Two teams with different Degradation in otherwise identical weekends get different favourite Strategies
- [ ] Fuel effect per lap is a setting with a default
- [ ] All tests go through the main seam

## Comments

**From ticket 01 (2026-10-19).** Where to plug in: `field_degradation()` in `src/f1_strategy/degradation.py` returns one rate per Compound for the whole field, and `predict()` uses it for every driver. Per-team Degradation means looking up the driver's team via `PreRaceInfo.teams` and simulating each driver with their team's rates (today every driver gets an identical prediction).

- Replace 01's placeholder fallback. A Compound with no Long Runs currently takes the mean of the *other Compounds'* rates. That is not the "field average" this ticket wants (the average across teams *on that Compound*); remove it rather than keep both.
- 01 clamps a negative fitted rate to 0. Fuel correction should make negative rates rarer; decide whether to keep the clamp.
- Gap to consider here: the simulation has no Compound pace (Softs quicker than Hards when fresh). Without it Softs only win on low Degradation and almost never appear as favourites. Per-team fits produce an intercept per Compound alongside the slope, so this is the natural place to add it. It is not in the spec yet; see the spec's Open questions.
- Tests: `tests/weekend_builder.py` has `degrading_run()` / `standard_practice()` for hand-built Long Runs; extend it with a fuel-burn helper rather than building laps inline.
