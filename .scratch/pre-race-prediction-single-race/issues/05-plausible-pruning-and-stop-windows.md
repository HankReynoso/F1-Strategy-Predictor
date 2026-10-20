# 05: Plausible pruning and Stop Windows

**What to build:** Only Plausible Candidate Strategies remain in a prediction: those whose Simulated Race Time is too far behind the fastest are dropped. Each planned stop gets a Stop Window covering every stop lap whose Simulated Race Time is within a small margin of the best, so flat trade-offs produce wide windows and sharp ones produce narrow windows. The Plausible margin, Stop Window margin and probability sharpness are settings with sensible defaults.

**Blocked by:** 01 (Tracer bullet)

**Status:** done

- [x] Candidate Strategies beyond the Plausible margin are excluded, and probabilities still sum to 100%
- [x] Each planned stop reports a Stop Window (first and last lap)
- [x] A weekend with low Degradation produces a wider Stop Window than one with high Degradation
- [x] Plausible margin, Stop Window margin and probability sharpness are settings
- [x] All tests go through the main seam

## Comments

**From ticket 01 (2026-10-19).** - Probability sharpness already exists: `Settings.probability_scale_s` (default 5 s; a Candidate Strategy this many seconds behind the fastest is e times less likely). Keep it rather than adding a second setting; rename if a clearer name emerges.
- Predictions currently list all 108 legal Strategies, so Plausible pruning makes a big difference to readability.
- Mirrored Strategies tie exactly (e.g. M → H and H → M have the same Simulated Race Time), because nothing in the model depends on which Compound comes first. They will always be pruned or kept together. Something like a heavier fuel load on the first Stint, or a starting-Compound rule, would break the tie; consider whether that belongs here or in a later spec.
- The simulator finds stint lengths by greedy allocation and returns one optimum. A Stop Window needs the Simulated Race Time as a function of each stop lap; for multi-stop Strategies, decide whether the other stops are re-optimised when one stop moves or held fixed. Re-optimising gives wider, more honest windows.

## Implementation notes

**Implemented (2026-10-19).** All work is behind the main seam, `predict(weekend, settings)`; tests are in `tests/test_pre_race_prediction.py` using the hand-built weekends in `tests/weekend_builder.py`. 13 tests pass (`uv run pytest`).

### What was built

- **Plausible pruning.** After simulating every legal Strategy, Candidate Strategies more than `Settings.plausible_margin_s` (default 20 s) behind the fastest are dropped, then probabilities are computed over what remains, so they still sum to 100%. On the standard 57-lap test weekend this cuts 108 Candidate Strategies to 22, none of them 3-stops.
- **Stop Windows.** `PlannedStop` now has `first_lap`, `best_lap` and `last_lap`. A stop lap is in the window when the Simulated Race Time with the stop on that lap is within `Settings.stop_window_margin_s` (default 1 s) of the best. On the test weekend windows are 7–11 laps wide.
- **Settings.** `plausible_margin_s` and `stop_window_margin_s` are new; probability sharpness stays as `probability_scale_s` (default 5 s), as ticket 01 suggested. I kept the name: it says what the number is (the e-folding scale in seconds) and no clearer name came up.
- **Simulator.** `simulate()` now returns only Simulated Race Time and Stint lengths; a separate `stop_windows()` is called only for Plausible Candidate Strategies, so the extra cost is paid on ~20 Strategies rather than 108. This kept the suite at ~1.4 s (it was ~3 s when windows were computed for everything).

### Decisions and reasoning

- **Other stops are re-optimised when one stop moves** (ticket 01's open question). To score stop k on lap p, the race is split at p and the Stints on each side are re-allocated optimally. Reasons: it is what a team would actually do (if you stop early you stretch the next Stint, not keep every other stop pinned), and it gives wider, more honest windows. Holding the others fixed was rejected as too narrow: for H → M → H on the test weekend it gives laps 18–26 / 31–39 against 17–27 / 30–40 re-optimised. A test pins the re-optimised values, worked out by brute force over every pair of stop laps independently of the code.
- **Windows are always one unbroken lap range.** Splitting the convex, separable Stint cost at p and re-optimising each side gives a time that is convex in p, so "first and last lap within the margin" never hides a gap.
- **Defaults.** Plausible margin 20 s: with a 5 s probability scale a 20 s gap already carries about 2% weight, so anything beyond adds clutter, not information. Stop Window margin 1 s: gives 7–11 lap windows at typical Degradation, close to the width commentators quote. Both are placeholders until the Backtest exists (spec: tuning is out of scope).
- **Pruning is relative to the driver's own fastest Candidate Strategy**, not to an absolute time, because the base pace placeholder makes absolute Simulated Race Time meaningless (spec Open questions).

### Deviations from the ticket or spec

- The ticket 01 test that lists every legal Strategy now passes `Settings(plausible_margin_s=math.inf)`, since default predictions are pruned. Its intent (enumeration is complete before pruning) is unchanged.
- The spec's wording of user story 32 and the Race simulator module now say that the other stops are re-optimised as one stop moves. This sharpens the spec rather than changing its intent.

### TDD note

The Stop Window, Plausible and Settings tests went red first. The two-stop re-optimisation test and the low/high Degradation test went green on first run, because the re-optimisation rule was chosen while making the first Stop Window test pass. They are kept as specification of that behaviour; the brute-force check shows the two-stop test would fail under the held-fixed alternative (the low/high Degradation test uses a 1-stop, where the two rules agree). My first hand estimate for the low/high Degradation widths (±4 vs ±3 laps) was loose because the best lap is off-centre; the test now pins the exact values (17–25 vs 18–23) from a direct calculation.

### Open questions, limitations and follow-ups

- **Mirrored Strategies still tie** (M → H and H → M), so they are always kept or pruned together and share probability equally. Not fixed here: breaking the tie needs a modelling choice (fuel load on the first Stint, a starting-Compound rule, or Compound pace) that belongs with fuel correction (02/03) or later. Filed as ticket 09 (needs-triage).
- **Consecutive Stop Windows can overlap.** With re-optimisation, e.g. H → S → H gives 19–29 and 28–38. Each window is honest on its own, but the scorer (06) should score each actual stop against its own window by position, not by "which window contains this lap". Noted on ticket 06.
- **Back-to-back same Compound** (H → H → M) is legal and Plausible; the stop between the two Hards is a fresh-set stop. Real but rarely planned; Remaining Sets (04) will prune some of these.
- Stop Windows are only as good as the Degradation model; they share ticket 01's gaps (field-wide rates, no fuel correction, no Compound pace).

### Review feedback for the user

- Default margins are guesses; expect the Backtest to move them. The Plausible margin interacts with `probability_scale_s` (the margin only matters for the tail), so tune them together.
- `stop_windows()` re-runs the greedy allocator for every lap of every stop: fine at ~20 Strategies × 57 laps, but if live Replay recomputes this every lap, a closed-form or cached version may be worth it.
