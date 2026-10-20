# 05: Plausible pruning and Stop Windows

**What to build:** Only Plausible Candidate Strategies remain in a prediction: those whose Simulated Race Time is too far behind the fastest are dropped. Each planned stop gets a Stop Window covering every stop lap whose Simulated Race Time is within a small margin of the best, so flat trade-offs produce wide windows and sharp ones produce narrow windows. The Plausible margin, Stop Window margin and probability sharpness are settings with sensible defaults.

**Blocked by:** 01 (Tracer bullet)

**Status:** ready-for-agent

- [ ] Candidate Strategies beyond the Plausible margin are excluded, and probabilities still sum to 100%
- [ ] Each planned stop reports a Stop Window (first and last lap)
- [ ] A weekend with low Degradation produces a wider Stop Window than one with high Degradation
- [ ] Plausible margin, Stop Window margin and probability sharpness are settings
- [ ] All tests go through the main seam

## Comments

**From ticket 01 (2026-10-19).** - Probability sharpness already exists: `Settings.probability_scale_s` (default 5 s; a Candidate Strategy this many seconds behind the fastest is e times less likely). Keep it rather than adding a second setting; rename if a clearer name emerges.
- Predictions currently list all 108 legal Strategies, so Plausible pruning makes a big difference to readability.
- Mirrored Strategies tie exactly (e.g. M → H and H → M have the same Simulated Race Time), because nothing in the model depends on which Compound comes first. They will always be pruned or kept together. Something like a heavier fuel load on the first Stint, or a starting-Compound rule, would break the tie; consider whether that belongs here or in a later spec.
- The simulator finds stint lengths by greedy allocation and returns one optimum. A Stop Window needs the Simulated Race Time as a function of each stop lap; for multi-stop Strategies, decide whether the other stops are re-optimised when one stop moves or held fixed. Re-optimising gives wider, more honest windows.
