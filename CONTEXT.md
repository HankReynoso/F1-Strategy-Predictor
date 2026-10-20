# F1 Strategy Predictor

Predicts which race strategies Formula 1 drivers are likely to be on, before and during a race, from historical races, the weekend's practice sessions, and live race data.

## Language

### Strategies

**Strategy**:
A driver's planned way through a race tyre-wise: the number of pit stops, the sequence of compounds, and a Stop Window for each stop.
_Avoid_: plan, tyre plan, pit plan

**Stint**:
A continuous run of laps on one set of tyres, between the start or a pit stop and the next pit stop or the finish.
_Avoid_: run (except "long run" in practice)

**Compound**:
The tyre type fitted for a Stint, named by its race designation (Soft, Medium, Hard, Intermediate, Wet) rather than Pirelli's C1–C5 codes.
_Avoid_: tyre, rubber

**Stop Window**:
The range of laps in which a planned pit stop is expected to happen.
_Avoid_: pit window (fine in speech), stop lap

**Deviation**:
A departure from a driver's planned Strategy in response to race events, such as pitting under a Safety Car. A Deviation is not itself part of a Strategy.
_Avoid_: reactive strategy, strategy change

### Predictions

**Candidate Strategy**:
One Strategy that a driver could plausibly be on, considered as an option when predicting.
_Avoid_: option, scenario

**Strategy Prediction**:
A ranked set of Candidate Strategies for one driver, each with a probability.
_Avoid_: forecast, guess

**Pre-race Prediction**:
A Strategy Prediction made after practice and qualifying, before the race starts.

**Live Prediction**:
A Strategy Prediction made during the race, updated as laps are completed.
_Avoid_: in-race forecast

**Backtest**:
Running Pre-race Predictions on past races and scoring them against the Strategies drivers actually ran.
