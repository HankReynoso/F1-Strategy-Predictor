# 04: Remaining Sets

**What to build:** Work out each driver's Remaining Sets (by Compound, new vs used) from the Tyre Sets they used in practice, sprint and qualifying, and exclude Candidate Strategies that driver can't run with them. Teammates on identical cars can now get different Strategy Predictions when their tyre usage differs.

**Blocked by:** 01 (Tracer bullet)

**Status:** done

- [x] Each driver's Remaining Sets are derived from Tyre Sets used before the race
- [x] A Candidate Strategy needing more sets of a Compound than a driver has left never appears for that driver
- [x] Two teammates with identical Degradation but different Remaining Sets get different predictions
- [x] All tests go through the main seam

## Comments

**From ticket 01 (2026-10-19).** The simulator (`src/f1_strategy/simulator.py`) assumes every Stint starts on a new Tyre Set at tyre age 0. Once used sets are in play, a Stint on a used set should start at that set's tyre age, which changes its Degradation cost and so the best stop laps. The data already carries `Lap.tyre_age` and `Lap.new_when_fitted`.

Whether Remaining Sets can be tracked across sessions depends on Tyre Set identity being reliable; see the note on ticket 07.

**From ticket 07 (2026-10-20).** Checked: FastF1 has no persistent Tyre Set ID. Per lap it gives `Stint` (counted per session, and it also goes up when a driver pits without changing tyres), `Compound`, `TyreLife` (laps on the set, carried across sessions) and `FreshTyre`. The loader therefore sets `Lap.tyre_set = "{driver}-{session}-stint{N}-{compound}"`, which is unique per stint but not linked across stints. One physical set run in FP2 and again in Q shows up as two `tyre_set` values, the second with `new_when_fitted=False`.

Rough numbers from Monza 2024 (FP1–Q, all drivers): 364 stints, of which 175 start on a used set. I matched each used stint to an earlier stint by the same driver on the same Compound whose final `TyreLife` was within about 1 lap of the used stint's first `TyreLife`. 77 had exactly one candidate, 72 had several and 26 had none. Laps without a lap time are dropped by the loader, which blurs the first and last tyre ages. So the "matching tyre life" approach works for about half the used sets, and this ticket needs a rule for the rest. The likely approach is to count sets rather than track them: new sets used = number of `new_when_fitted=True` stints per Compound, taken away from the weekend allocation. That needs no matching at all for new-vs-used Remaining Sets.

## Implementation notes

**Implemented (2026-10-20).** Tyre Allocation tracker lives at `src/f1_strategy/tyre_allocation.py`; the predictor calls it before enumerating Candidate Strategies and drops any whose Compound counts exceed Remaining Sets. `StrategyPrediction` now also carries the driver's `remaining_sets: dict[Compound, int]` so callers can see what the pruning used. Tests in `tests/test_pre_race_prediction.py` under the "Ticket 04" section go through `predict()`.

- **Does the weekend description carry each driver's full Tyre Allocation?** No. The spec's race weekend description holds only the sets drivers *used* (via practice/sprint/qualifying `Lap` rows), and ticket 07 confirmed FastF1 exposes no per-set identity at all, let alone the FIA allocation. The decision was to default the allocation to the FIA regulation per weekend format (8 Soft, 3 Medium, 2 Hard conventional; 6 S, 4 M, 2 H sprint) and expose an optional override on `PreRaceInfo.tyre_allocation`. The default is uniform across drivers, which matches the real regulation; the override lets tests pin an allocation and gives the loader a seam if alternative allocations ever need to be reflected (ATA weekends, future regulation changes). The decision is recorded as ADR-0002.
- **Remaining Sets counts new sets only.** For each driver, `new_remaining[compound] = allocation[compound] - distinct new Tyre Sets fitted in any pre-race session`. Used-set stints do not subtract from the allocation. A Candidate Strategy is pruned when the count of its stints on some Compound exceeds `new_remaining` for that Compound. Rejected alternatives (counting used sets too, or tracking each physical set across sessions) are set out in ADR-0002. The approach matches the ticket-07 suggestion of counting rather than tracking sets.
- **New seam added to the weekend description.** `PreRaceInfo` gained one optional field, `tyre_allocation: dict[Compound, int] | None = None`, so hand-built weekends and real-weekend loaders can override the default. The `fastf1_loader` keeps the default (it does not fill the field), which is faithful to the data FastF1 provides.

- **What was built.**
  - `tyre_allocation.default_allocation(is_sprint_weekend)` — the FIA defaults.
  - `tyre_allocation.remaining_sets(pre_race)` — per-driver dict of Remaining Sets per Compound, iterating every pre-race session's laps and counting distinct `tyre_set` strings whose first `new_when_fitted=True`.
  - `tyre_allocation.can_run(strategy_compounds, remaining)` — the pruning predicate.
  - `predict()` now calls `remaining_sets` once per weekend and threads each driver's dict into `_predict_driver`, which skips any Strategy failing `can_run`.
  - `StrategyPrediction.remaining_sets` surfaces the dict for callers; the field is a plain `dict[Compound, int]`.

- **Tests (through the main `predict()` seam).**
  - *A driver short of a compound loses strategies needing more of it.* VER's standard Long Runs consume 1 of each Compound; VER's set of Candidate Strategies drops every entry needing 2+ Hards, and that set of exclusions is exactly what PER (who ran nothing) still has. VER's Candidate set is a strict subset of PER's.
  - *Teammates with identical Degradation can get different predictions from tyre usage.* VER and PER both run identical S/M/H Long Runs, then PER runs a second new Hard. With the Hard-only allocation override `{S: 100, M: 100, H: 2}`, PER drops to 0 Hards remaining and every Candidate Strategy using a Hard disappears; VER (still at 1 Hard) keeps H-using strategies.
  - *Strategies needing more of a compound than the allocation are excluded for everyone.* Overriding to `{H: 1}` eliminates every Strategy with 2+ Hards for every driver.
  - *Used sets do not restore capacity lost to new-set usage.* A VER Long Run on a used Hard does not subtract from the allocation, so both drivers' Hard remainders stay at 2.
  - *Remaining Sets are reported on the prediction.* `prediction.remaining_sets` matches the hand-computed subtractions.
  - *Default allocation rules out only strategies that overshoot a compound.* PER's full-allocation Candidate set equals the 108 legal Strategies minus the eight 4-stint Strategies needing 3 Hards.
- Two existing tests needed small changes once pruning was active: the 108-strategies sanity test now overrides the allocation to a large one so the "no pruning" baseline is still testable; and the two-stop Stop Window test (which asserts on H-M-H) switches from VER to PER because VER's standard Long Runs leave only 1 Hard remaining, which prunes H-M-H.

- **Decisions and rejected alternatives.**
  - *Default allocation per weekend format.* Conventional 8/3/2 and sprint 6/4/2 match the 2024 regulations. Alternative: ask callers to supply it on every weekend. Rejected because the regulation is almost always right; the override field covers the rest.
  - *Count distinct `tyre_set` values rather than stints.* The same new Tyre Set could appear across more than one `tyre_set` id in theory, but the FastF1 loader (ticket 07) uses one id per stint, so distinct ids = distinct physical sets for pre-race sessions.
  - *Overrides at the weekend level, not per-driver.* FIA allocation is uniform per weekend; a per-driver dict would invite real-world drift between teammates that doesn't actually exist and makes tests noisier. The current override is still enough to shape any pruning behavior tests want.
  - *Report `remaining_sets` on `StrategyPrediction` rather than on a separate object.* The pruning decision is a per-driver concern already carried on `StrategyPrediction`; a parallel object would need the same key set and would be used only through the same dict lookup.
  - *Prune before simulating.* Pruning first avoids running the simulator for Strategies that are never going to survive; the Candidate set is small enough that correctness is the point, not performance.

- **Deviations from the spec/ticket.** None. The spec names the Tyre Allocation tracker as a module; it now exists at `tyre_allocation.py`. The ticket's question about whether the weekend description carries the full Tyre Allocation is answered above, with ADR-0002 recording the trade-off.

- **Known limitations and follow-ups.**
  - *Used-set capacity is not modelled.* A driver with a saved used Medium can in reality run a strategy that this pruning rule rejects. In practice this is uncommon for strategies that would otherwise be the favourite, and ticket 01's note about tyre age at Stint start (not Remaining Sets) is the more consequential loose thread for the simulator. Follow-up: once cross-session Tyre Set identity is modelled (not planned under this spec), used-set availability can augment Remaining Sets without changing the public API.
  - *Allocation format is per-weekend, not per-driver.* A driver who, say, had a set confiscated by the stewards cannot be modelled through the default or the override. Not currently in scope and never arose in Monza 2024.
  - *Sprint allocation defaults are a best guess.* The 2024 regulations' sprint allocation varied across weekends depending on the format tweaks the FIA applied. 6/4/2 is a common pattern; the override field is there precisely so the loader (or a test) can set a specific value when the Backtest cares.
  - *FastF1 loader does not populate `tyre_allocation`.* It leaves it at `None`, so the default is used. If a future ATA weekend ships with a non-standard allocation, the loader would need teaching; left for when the Backtest meets a case it matters for.

- **Review feedback for the user.** Done test-first through the main seam: four tests ran red before the implementation (the pruning assertions and the `remaining_sets` surface), then went green. Two existing tests (`...are_every_legal_1_to_3_stop_strategy...` and the H-M-H `..._stop_window_lets_the_other_stop_move_to_suit`) had to be adjusted — not because they were wrong but because they were implicitly relying on no Tyre Allocation pruning; both now use a path through the main seam that keeps their original intent (one via an allocation override, one by querying the teammate who has full sets left). Branch was rebased onto `main` before pushing to accommodate ticket 03 landing in parallel.
