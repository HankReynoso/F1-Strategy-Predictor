# 02: Per-team Degradation with fuel correction

**What to build:** Replace the field-wide Degradation with Degradation fitted per Compound per team from fuel-corrected Long Run laps, falling back to the field average when a team has no Long Runs on a Compound. Each Degradation estimate reports where it came from. Teams that wear their tyres harder now get different favourite Strategies from teams that don't. The fuel effect per lap is a setting with a sensible default.

**Blocked by:** 01 (Tracer bullet)

**Status:** done

- [x] Degradation is estimated per team per Compound from Long Runs
- [x] Long Run lap times are corrected for fuel burn before fitting, so a Long Run that gets faster from fuel alone shows no false improvement
- [x] A team with no Long Runs on a Compound uses the field average for it
- [x] Predictions expose each team's Degradation source per Compound (Long Runs or field average)
- [x] Two teams with different Degradation in otherwise identical weekends get different favourite Strategies
- [x] Fuel effect per lap is a setting with a default
- [x] All tests go through the main seam

## Comments

**From ticket 01 (2026-10-19).** Where to plug in: `field_degradation()` in `src/f1_strategy/degradation.py` returns one rate per Compound for the whole field, and `predict()` uses it for every driver. Per-team Degradation means looking up the driver's team via `PreRaceInfo.teams` and simulating each driver with their team's rates (today every driver gets an identical prediction).

- Replace 01's placeholder fallback. A Compound with no Long Runs currently takes the mean of the *other Compounds'* rates. That is not the "field average" this ticket wants (the average across teams *on that Compound*); remove it rather than keep both.
- 01 clamps a negative fitted rate to 0. Fuel correction should make negative rates rarer; decide whether to keep the clamp.
- Gap to consider here: the simulation has no Compound pace (Softs quicker than Hards when fresh). Without it Softs only win on low Degradation and almost never appear as favourites. Per-team fits produce an intercept per Compound alongside the slope, so this is the natural place to add it. It is not in the spec yet; see the spec's Open questions.
- Tests: `tests/weekend_builder.py` has `degrading_run()` / `standard_practice()` for hand-built Long Runs; extend it with a fuel-burn helper rather than building laps inline.

## Implementation notes

**What was built.** `degradation.team_degradation()` replaces `field_degradation()`. It groups Long Runs by (team, Compound), fits a pooled within-run least-squares slope of lap time against tyre age, and adds the fuel effect setting back on. A team with no Long Runs on a Compound takes the mean of the fitted rates from teams that do (`DegradationSource.FIELD_AVERAGE`); its own fit is tagged `DegradationSource.LONG_RUNS`. `predict()` runs the simulator once per driver with their team's rates, and each `StrategyPrediction` now carries a `team_degradation: dict[Compound, DegradationEstimate]`. `Settings.fuel_effect_s_per_lap` defaults to `0.03`.

**Decisions.**
- *Degradation default fallback dropped.* 01's "mean of the other Compounds' fitted rates" fallback is removed, as the ticket asked. If no team in the field has Long Runs on a Compound, `team_degradation()` raises; the strategy generator covers all three dry Compounds, so a predictor that silently invented a rate for a Compound no one has driven would hide a real data gap. Push Lap fall-off (spec story 27) is the next layer; the ticket doesn't require it.
- *Negative-slope clamp kept.* Fuel correction lifts fitted rates by the fuel effect, which makes a negative fit much rarer, but a short, noisy Long Run can still produce one. Clamping at zero avoids a negative Degradation rate propagating into Simulated Race Time, where it would make longer Stints look faster. The alternative (letting the fit go negative and relying on later layers to catch it) was rejected because nothing downstream currently does.
- *Fuel correction as a slope lift.* Within one Long Run the lap counter and tyre age move together, so fuel correction collapses to adding the fuel-effect setting to the fitted slope rather than transforming each lap individually. Equivalent in result, simpler to read.
- *Fuel effect default `0.03 s/lap`.* A conservative placeholder in the published range for current regulations; the spec expects every setting to be Backtest-tuned later.
- *`team_degradation` lives on `StrategyPrediction`, not a sibling return.* Driver-indexed access matches the rest of the public shape (every observable about a driver's prediction hangs off that driver). The redundancy between teammates is cheap.
- *`degrading_run()` grew a `fuel_burn` parameter rather than a sibling helper.* The ticket's comment asked for a fuel helper on the builder; adding a parameter with the same default as `Settings.fuel_effect_s_per_lap` keeps the existing tests' hand-worked numbers intact (fitted Degradation still equals the helper argument) and lets new tests dial fuel burn independently.

**Ticket 09 (mirrored Strategy ties).** Checked whether fuel correction naturally breaks the M → H vs H → M tie. It does not: the simulator's cost is still a sum over Stints of `d_c * L * (L - 1) / 2 + base * L`, and fuel burn adds the same `fuel_effect * race_laps * (race_laps - 1) / 2` to every Strategy regardless of order. Compound pace from a per-Compound intercept would behave the same way as long as the simulator stays strategy-order-agnostic. Breaking mirrors needs a cost term that couples compound choice to absolute race lap (e.g. degradation scaling with fuel load, or a starting-Compound rule). Left for ticket 09; this ticket is unchanged by that decision.

**Open questions / follow-ups.**
- Push Lap fall-off fallback (spec story 27) sits between Long Runs and the field average and is not wired up yet; a follow-up ticket should add it once Push Lap detection exists.
- `team_degradation()` currently raises if no team drove a dry Compound at all. Realistic for a sprint weekend with a wet-affected FP1; may need a graceful fallback later.
- Compound pace (spec Open questions) still waits on `/domain-modeling`; adding a per-Compound intercept to the fit is cheap once a term is agreed.

**Review feedback to the user.** None.
