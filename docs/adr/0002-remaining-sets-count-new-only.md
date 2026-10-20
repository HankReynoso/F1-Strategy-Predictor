# Remaining Sets counts new sets only, from a defaulted Tyre Allocation

The Tyre Allocation tracker computes each driver's Remaining Sets per Compound as `allocation − distinct new Tyre Sets fitted in pre-race sessions`. Used-set stints are left out of the subtraction. The allocation itself is uniform across drivers and defaults to the FIA regulation (8 Soft, 3 Medium, 2 Hard for a conventional weekend; 6 S, 4 M, 2 H for a sprint weekend), with an optional per-weekend override on `PreRaceInfo.tyre_allocation`.

A Candidate Strategy is excluded for a driver when it needs more sets of some Compound than that driver has new sets remaining. Teammates on the same car can therefore get different predictions purely from their practice and qualifying tyre usage differing.

The weekend description does not carry the per-driver Tyre Allocation, because FastF1 does not expose it. The regulation allocation is the same for every driver on a given weekend format, so defaulting from the format is sound; the override field lets tests pin specific allocations and gives the loader a way to reflect alternative allocations (ATA weekends, future regulation changes) without a schema change.

Counting only new sets understates each driver's true pool: used sets saved from practice are legitimately available for the race. The understatement is small in practice because teams protect new sets for the race, and the alternative — tracking each physical set across sessions — needs cross-session Tyre Set identity that FastF1 does not provide (ticket 07 Implementation notes measure that matching succeeds for only about half of used stints). A conservative new-only count can prune a strategy that the driver could in fact have run on a used set, but it will never allow a strategy they cannot run; the simulation's main role is ranking strategies by Simulated Race Time, and a slightly tighter pool only ever shrinks the Candidate set.

## Amendment (2026-10-20): used-set fallback

The claim above that a new-only count "only ever shrinks the Candidate set" is wrong in one case: it can empty it. At Baku 2024 Alonso's new-only Remaining Sets (S=0, M=1, H=0) left no Strategy using two dry Compounds, and the predictor crashed (ticket 12). For a driver whose new-only count leaves no runnable Strategy, Remaining Sets are recounted including used sets seen in that driver's pre-race sessions, capped by the Tyre Allocation, and the prediction is flagged. If that still leaves nothing, the driver gets an unfiltered, flagged prediction. Other drivers keep the new-only count. The used-set count is an approximation, for the per-set identity reasons below.

## Considered Options

- **Track every physical set across sessions** (match used stints to earlier new ones by starting Tyre Life): rejected because FastF1 does not expose a persistent Tyre Set id and the Tyre Life matching heuristic is ambiguous for about half of used stints (ticket 07). The precision gained is small and the data pipeline becomes brittle to FastF1 cleanup.
- **Count new + used sets, ignoring regulation-mandated set returns**: rejected because it overstates the pool by the ~7 sets every driver must return by the end of qualifying, and modelling the return schedule needs the same per-set identity we rejected above.
- **Require the loader (and hand-built weekends) to supply the full allocation**: rejected as the default. FIA allocation is uniform per weekend format, so a default is almost always right; the optional override covers the cases where it is not.
