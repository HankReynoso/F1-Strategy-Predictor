# 04: Remaining Sets

**What to build:** Work out each driver's Remaining Sets (by Compound, new vs used) from the Tyre Sets they used in practice, sprint and qualifying, and exclude Candidate Strategies that driver can't run with them. Teammates on identical cars can now get different Strategy Predictions when their tyre usage differs.

**Blocked by:** 01 (Tracer bullet)

**Status:** ready-for-agent

- [ ] Each driver's Remaining Sets are derived from Tyre Sets used before the race
- [ ] A Candidate Strategy needing more sets of a Compound than a driver has left never appears for that driver
- [ ] Two teammates with identical Degradation but different Remaining Sets get different predictions
- [ ] All tests go through the main seam
