# Historical information comes only from the same Regulation Era

Anything drawn from previous seasons (Historical Degradation, Pit Loss, and later Circuit Tendency and the other Tendencies) uses only races in the same Regulation Era as the race being predicted. 2022–2025 is one era; 2026 starts a new one, with new cars, power units and narrower tyres. Pooling across the change would feed the model tyre and car behaviour that no longer applies. The cost is that the first season of an era has no history at all: 2022 races run on this weekend's data alone, and 2026 races join the Backtest only once enough same-era history exists.

## Considered Options

- **Pool every season from 2022 on**: rejected because 2026 tyres and cars behave differently, and the error would be silent.
- **Pool across eras with a down-weighting**: rejected for now; there is no data yet to choose the weight, and it can be revisited once 2026 history exists.
