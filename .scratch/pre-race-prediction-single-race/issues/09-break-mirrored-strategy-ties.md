# 09: Break ties between mirrored Strategies

**What to build:** Make the order of Compounds affect Simulated Race Time, so that mirrored Strategies (e.g. M → H and H → M) no longer tie exactly. Today nothing in the model depends on which Compound comes first, so every mirrored pair has identical Simulated Race Time, is always kept or pruned together by the Plausible margin, and splits probability evenly. Real teams usually start on the softer Compound of a pair, so the tie costs Strategy Match.

**Blocked by:** None for the decision; likely implemented alongside fuel correction (02/03) or Compound pace (spec Open questions).

**Status:** needs-triage

Options to decide between (needs a modelling choice, possibly via `/domain-modeling`):
- Fuel load: the first Stint runs heavier, so Degradation (or pace) costs more early, favouring a harder Compound or shorter first Stint.
- Compound pace: softer Compounds are quicker when fresh, which matters most at the start where track position counts.
- A starting-Compound rule or tendency from history (overlaps Circuit Tendency, ADR-0001).

- [ ] Mirrored Strategies get different Simulated Race Times on a hand-built weekend
- [ ] The chosen mechanism is recorded in the spec and, if new, in `CONTEXT.md`
- [ ] All tests go through the main seam

## Comments

**From ticket 05 (2026-10-19).** Raised in ticket 01, deferred in 05 because it needs a modelling choice outside Plausible pruning and Stop Windows.

**From ticket 02 (2026-10-20).** Fuel correction (ticket 02) does not break mirrored ties by itself: the simulator's cost is a sum over Stints of `d_c * L * (L - 1) / 2 + base * L`, and total fuel burn is `fuel_effect * race_laps * (race_laps - 1) / 2` regardless of Compound order. The same holds for a per-Compound pace intercept while the simulator stays order-agnostic. Breaking mirrors needs a term that depends on absolute race-lap position of each Stint, e.g. degradation scaling with fuel load (heavy fuel wears tyres more early), or a starting-Compound rule. Still needs the modelling choice before implementation.
