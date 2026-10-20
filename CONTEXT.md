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

**Dry Race**:
A race run entirely on dry Compounds (Soft, Medium, Hard). In a Dry Race a driver must use at least two different dry Compounds. Only Dry Races are in scope.
_Avoid_: normal race

### Tyres and pace

**Tyre Set**:
One set of four tyres of a single Compound, either new or used.
_Avoid_: tyre, set of tyres

**Tyre Allocation**:
The Tyre Sets a driver has for a race weekend. The sets still usable in the race are the driver's **Remaining Sets**.
_Avoid_: tyre inventory, stock

**Degradation**:
The lap time a Compound loses per lap as it wears.
_Avoid_: deg (fine in speech), tyre wear, drop-off

**Long Run**:
A practice Stint run at race pace on a heavy fuel load, used to measure Degradation. On sprint weekends, sprint race Stints also count as Long Runs.
_Avoid_: race sim, race run

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

**Plausible**:
Describes a Candidate Strategy that is legal, runnable with the driver's Remaining Sets, and within a margin of the fastest simulated race time.

### History

**Circuit Tendency**:
How often each stop count and Compound sequence has been run at a circuit in past Dry Races, with recent seasons counting more.

**Team Tendency**:
How conservative or aggressive a team's strategy choices have been compared with the rest of the field.

**Situational Tendency**:
How strategy choices shift with a driver's circumstances, such as starting position.

### Evaluation

**Backtest**:
Running Strategy Predictions on past races and scoring them against the Strategies drivers actually ran.

**Strategy Match**:
A prediction whose stop count and Compound sequence equal what the driver actually ran. Stop Window accuracy is scored separately.
_Avoid_: hit, correct prediction

**Neutralised Race**:
A race that had a Safety Car or Virtual Safety Car period. Scored separately in Backtests because its Deviations can't be predicted beforehand.
_Avoid_: SC race, disrupted race

**Replay**:
Feeding a past race to Live Predictions lap by lap, revealing only what was known at each lap.
_Avoid_: simulation, playback
