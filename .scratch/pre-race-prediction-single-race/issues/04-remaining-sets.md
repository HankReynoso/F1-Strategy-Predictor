# 04: Remaining Sets

**What to build:** Work out each driver's Remaining Sets (by Compound, new vs used) from the Tyre Sets they used in practice, sprint and qualifying, and exclude Candidate Strategies that driver can't run with them. Teammates on identical cars can now get different Strategy Predictions when their tyre usage differs.

**Blocked by:** 01 (Tracer bullet)

**Status:** ready-for-agent

- [ ] Each driver's Remaining Sets are derived from Tyre Sets used before the race
- [ ] A Candidate Strategy needing more sets of a Compound than a driver has left never appears for that driver
- [ ] Two teammates with identical Degradation but different Remaining Sets get different predictions
- [ ] All tests go through the main seam

## Comments

**From ticket 01 (2026-10-19).** The simulator (`src/f1_strategy/simulator.py`) assumes every Stint starts on a new Tyre Set at tyre age 0. Once used sets are in play, a Stint on a used set should start at that set's tyre age, which changes its Degradation cost and so the best stop laps. The data already carries `Lap.tyre_age` and `Lap.new_when_fitted`.

Whether Remaining Sets can be tracked across sessions depends on Tyre Set identity being reliable; see the note on ticket 07.

**From ticket 07 (2026-10-20).** Checked: FastF1 has no persistent Tyre Set ID. Per lap it gives `Stint` (counted per session, and it also goes up when a driver pits without changing tyres), `Compound`, `TyreLife` (laps on the set, carried across sessions) and `FreshTyre`. The loader therefore sets `Lap.tyre_set = "{driver}-{session}-stint{N}-{compound}"`, which is unique per stint but not linked across stints. One physical set run in FP2 and again in Q shows up as two `tyre_set` values, the second with `new_when_fitted=False`.

Rough numbers from Monza 2024 (FP1–Q, all drivers): 364 stints, of which 175 start on a used set. I matched each used stint to an earlier stint by the same driver on the same Compound whose final `TyreLife` was within about 1 lap of the used stint's first `TyreLife`. 77 had exactly one candidate, 72 had several and 26 had none. Laps without a lap time are dropped by the loader, which blurs the first and last tyre ages. So the "matching tyre life" approach works for about half the used sets, and this ticket needs a rule for the rest. The likely approach is to count sets rather than track them: new sets used = number of `new_when_fitted=True` stints per Compound, taken away from the weekend allocation. That needs no matching at all for new-vs-used Remaining Sets.
