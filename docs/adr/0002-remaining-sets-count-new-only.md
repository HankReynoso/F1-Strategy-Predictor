# Remaining Sets counts new sets only, from a defaulted Tyre Allocation

The Tyre Allocation tracker computes each driver's Remaining Sets per Compound as `allocation − distinct new Tyre Sets fitted in pre-race sessions`. Used-set stints are left out of the subtraction. The allocation itself is uniform across drivers and defaults to the FIA regulation (8 Soft, 3 Medium, 2 Hard for a conventional weekend; 6 S, 4 M, 2 H for a sprint weekend), with an optional per-weekend override on `PreRaceInfo.tyre_allocation`.

A Candidate Strategy is excluded for a driver when it needs more sets of some Compound than that driver has new sets remaining. Teammates on the same car can therefore get different predictions purely from their practice and qualifying tyre usage differing.

The weekend description does not carry the per-driver Tyre Allocation, because FastF1 does not expose it. The regulation allocation is the same for every driver on a given weekend format, so defaulting from the format is sound; the override field lets tests pin specific allocations and gives the loader a way to reflect alternative allocations (ATA weekends, future regulation changes) without a schema change.

Counting only new sets understates each driver's true pool: used sets saved from practice are legitimately available for the race. The understatement is small in practice because teams protect new sets for the race, and the alternative — tracking each physical set across sessions — needs cross-session Tyre Set identity that FastF1 does not provide (ticket 07 Implementation notes measure that matching succeeds for only about half of used stints). A conservative new-only count can prune a strategy that the driver could in fact have run on a used set, but it will never allow a strategy they cannot run; the simulation's main role is ranking strategies by Simulated Race Time, and a slightly tighter pool only ever shrinks the Candidate set.

## Amendment (2026-10-20): used-set fallback

The claim above that a new-only count "only ever shrinks the Candidate set" is wrong in one case: it can empty it. At Baku 2024 Alonso's new-only Remaining Sets (S=0, M=1, H=0) left no Strategy using two dry Compounds, and the predictor crashed (ticket 12). For a driver whose new-only count leaves no runnable Strategy, Remaining Sets are recounted including used sets seen in that driver's pre-race sessions, capped by the Tyre Allocation, and the prediction is flagged. If that still leaves nothing, the driver gets an unfiltered, flagged prediction. Other drivers keep the new-only count. The used-set count is an approximation, for the per-set identity reasons below.

Concretely (ticket 12 implementation): the used-set count per Compound is the number of distinct `tyre_set` ids whose first lap had `new_when_fitted=False`, capped by the Tyre Allocation. Because the FastF1 loader assigns a per-stint id, one physical used set fitted in two sessions registers as two ids and the fallback over-counts; the allocation cap bounds the error, and the flag on the prediction (`USED_SET_FALLBACK` or `UNFILTERED_FALLBACK`) tells callers that this driver's Remaining Sets is the approximate used-inclusive count rather than the exact new-only count. Being slightly over-permissive is preferable to the crash it replaces.

## Amendment (2026-10-27): per-source rule, OpenF1 weekends get the full allocation

The new-only count needs to know which Tyre Sets were new when fitted. FastF1 (2022) reads that from F1's own timing feed (`FreshTyre`). OpenF1 (2023 onward, [ADR-0006](0006-per-season-data-source.md)) has no such flag: the loader inferred it from `tyre_age_at_start == 0`, and in practice and qualifying OpenF1 often reports 0 on a stint that continues or re-fits a set already used. Over the 70 cached 2023–2025 weekends, 393 of 1,395 race starters show more "new" sets of some Compound than the Tyre Allocation, which is impossible. In the 2026-10-27 baseline 26% of OpenF1-era driver predictions fell back (used-set or unfiltered), against 2% on FastF1. No rule tried during triage recovered the true count (back-to-back stints as one set, practice-only continuation, capping): each rests on an unvalidated guess, and the race can't be used to check a pre-race count without leaking the outcome. Measurements are in [ticket 50](../../.scratch/full-backtest/issues/50-openf1-counts-refitted-sets-as-new.md).

So the rule is now per source:

- **FastF1 (2022 and earlier):** unchanged. New-only count with the used-set and unfiltered fallbacks above.
- **OpenF1 (2023 onward):** every driver's Remaining Sets is the full Tyre Allocation, and the prediction is labelled `FULL_ALLOCATION` ("full allocation (set usage unknown)") so the single-race report shows it the way it shows the fallbacks. The fallbacks never apply.

The weekend description carries this as `PreRaceInfo.set_usage_known` (False from the OpenF1 loader), read only by the Tyre Allocation tracker. `Lap.new_when_fitted` is still derived from `tyre_age_at_start` and `tyre_set` ids are unchanged, so Long Run classification and Degradation don't move. Setting `new_when_fitted=False` on every OpenF1 lap was rejected: it would make the weekend claim every set was used rather than say usage is unknown, and the used-set fallback would then read it as data.

With Remaining Sets no longer pruning 2023+ predictions, the allocation itself matters. The two 2023 Alternative Tyre Allocation weekends (Hungary and Monza: 4 Soft, 4 Medium, 3 Hard) now set `PreRaceInfo.tyre_allocation` through the override this ADR already provides.

The full allocation overstates what a driver has in the race, since regulation set returns and practice wear aren't counted. This is the permissive side of the trade-off the original decision made conservatively: it can allow a Strategy a driver couldn't run, but never rules out one they could. The decision rests on the data, not the score: OpenF1 doesn't say which sets were new, and this is the only option that doesn't guess. Whether 2022 should follow, so the two sources share one rule, is [ticket 51](../../.scratch/full-backtest/issues/51-new-only-remaining-sets-rule-out-actual-strategies.md).

## Considered Options

- **Track every physical set across sessions** (match used stints to earlier new ones by starting Tyre Life): rejected because FastF1 does not expose a persistent Tyre Set id and the Tyre Life matching heuristic is ambiguous for about half of used stints (ticket 07). The precision gained is small and the data pipeline becomes brittle to FastF1 cleanup.
- **Count new + used sets, ignoring regulation-mandated set returns**: rejected because it overstates the pool by the ~7 sets every driver must return by the end of qualifying, and modelling the return schedule needs the same per-set identity we rejected above.
- **Require the loader (and hand-built weekends) to supply the full allocation**: rejected as the default. FIA allocation is uniform per weekend format, so a default is almost always right; the optional override covers the cases where it is not.
