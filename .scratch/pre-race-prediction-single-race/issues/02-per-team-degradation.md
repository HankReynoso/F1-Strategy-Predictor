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
