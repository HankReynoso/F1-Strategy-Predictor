# Degradation for an unrun Compound comes from circuit race history, then a next-softer bound

When no team has Long Runs or Push Laps on a dry Compound this weekend, its Degradation is estimated from previous seasons' race Stints at the same circuit (current regulations, recent seasons counting more, never the race being predicted). If that history is missing, the next-softer Compound's field-average Degradation is used as an upper bound, on the assumption that a harder Compound wears no faster. Each estimate keeps its source. This amends ticket 02's decision to refuse rather than invent a rate: teams routinely save the Hard for the race, so refusing made 3 of 7 recent 2024 races unpredictable (ticket 08), and race Stints are real race running on exactly that Compound.

## Considered Options

- **Keep refusing** (ticket 02): rejected because it rules out a large share of races, including Monza, Abu Dhabi and Las Vegas 2024.
- **Fit shorter practice runs for that Compound only**: rejected because the runs that exist are one or two laps, noisier than any fallback, and at Monza 2024 there is still almost nothing to fit.
- **Next-softer bound alone**: kept only as the last step, because it ignores real data that is usually available.

## Implementation note (2026-10-20)

The chain resolves softer→harder across dry Compounds. If the next-softer Compound was also unrun this weekend, its own fallback (likely history) is already resolved by the time the harder Compound reads it, so the bound chain propagates through intermediate gaps. SOFT has no softer bound; if Soft is unrun, no history exists for it and no softer Compound is available, the predictor raises a clear refusal and the command exits with code 2.
