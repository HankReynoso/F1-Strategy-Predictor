# Combine race simulation with historical tendencies

Strategy Predictions score each Candidate Strategy by simulated race time (from this weekend's Long Runs) and then weight it by how often similar strategies were chosen historically (Circuit Tendency, later Team and Situational Tendencies). How much the simulated time gap counts against history is tuned by Backtesting, not hand-picked. We did this because pure simulation predicts what is *fastest*, not what teams actually *choose* (they hedge, react to rivals, and are bound by their Remaining Sets), while pure history ignores this weekend's Degradation.

## Considered Options

- **Simulation only** (assume teams pick the fastest Strategy): rejected because real choices regularly differ from the theoretical optimum.
- **History only** (learn choices from past races): rejected because it can't respond to a weekend where tyres behave unusually.
