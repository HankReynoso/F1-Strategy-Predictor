# 05: Plausible pruning and Stop Windows

**What to build:** Only Plausible Candidate Strategies remain in a prediction: those whose Simulated Race Time is too far behind the fastest are dropped. Each planned stop gets a Stop Window covering every stop lap whose Simulated Race Time is within a small margin of the best, so flat trade-offs produce wide windows and sharp ones produce narrow windows. The Plausible margin, Stop Window margin and probability sharpness are settings with sensible defaults.

**Blocked by:** 01 (Tracer bullet)

**Status:** ready-for-agent

- [ ] Candidate Strategies beyond the Plausible margin are excluded, and probabilities still sum to 100%
- [ ] Each planned stop reports a Stop Window (first and last lap)
- [ ] A weekend with low Degradation produces a wider Stop Window than one with high Degradation
- [ ] Plausible margin, Stop Window margin and probability sharpness are settings
- [ ] All tests go through the main seam
