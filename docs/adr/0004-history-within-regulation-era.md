# Historical information comes only from the same Regulation Era

Anything drawn from previous seasons (Historical Degradation, Pit Loss, and later Circuit Tendency and the other Tendencies) uses only races in the same Regulation Era as the race being predicted. 2022–2025 is one era; 2026 starts a new one, with new cars, power units and narrower tyres. Pooling across the change would feed the model tyre and car behaviour that no longer applies. The cost is that the first season of an era has no history at all: 2022 races run on this weekend's data alone, and 2026 races join the Backtest only once enough same-era history exists.

## Exception: Pit Loss

Pit Loss may draw on races from before the Regulation Era when the circuit has no same-era race to measure from. It depends mostly on the pit lane (its length and speed limit), not on the cars, so the reason for the era rule doesn't apply. Without this exception, every race in the first season of an era (all of 2022) would be an Excluded Race. Rare pit lane changes are ignored for now.

Since mid-October 2026 the 2018–2020 seasons can no longer be downloaded without an F1 TV subscription, and OpenF1 doesn't cover them, so this exception can't actually fire for the 2022 circuits whose only pre-era history is 2018–2019. See [ADR-0006](0006-per-season-data-source.md) for the per-season data-source policy and the pit-lane-table fallback that covers those five circuits.

## Considered Options

- **Pool every season from 2022 on**: rejected because 2026 tyres and cars behave differently, and the error would be silent.
- **Pool across eras with a down-weighting**: rejected for now; there is no data yet to choose the weight, and it can be revisited once 2026 history exists.
