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
The range of laps in which a planned pit stop is expected to happen: every stop lap whose Simulated Race Time, with the Strategy's other stops moved to suit, is within a margin of the best stop lap. Its width is the number of laps it spans, both ends counted ("lap 5–5" is 1 lap wide).
_Avoid_: pit window (fine in speech), stop lap

**Deviation**:
A departure from a driver's planned Strategy in response to race events, such as pitting under a Safety Car. A Deviation is not itself part of a Strategy.
_Avoid_: reactive strategy, strategy change

**Remaining Strategy**:
The Strategy for the rest of a race from a driver's current lap, Compound fitted and Remaining Sets. Live Predictions predict Remaining Strategies after a Deviation.
_Avoid_: new strategy, revised plan

**Dry Race**:
A race run entirely on dry Compounds (Soft, Medium, Hard). In a Dry Race a driver must use at least two different dry Compounds. Only Dry Races are in scope.
_Avoid_: normal race

### Tyres and pace

**Tyre Set**:
One set of four tyres of a single Compound, either new or used.
_Avoid_: tyre, set of tyres

**Tyre Allocation**:
The Tyre Sets a driver has for a race weekend. The sets still usable in the race are the driver's **Remaining Sets**: the allocation minus the new sets fitted before the race, when the data says which sets were new (FastF1, 2022), or the whole allocation when it doesn't (OpenF1, 2023 onward).
_Avoid_: tyre inventory, stock

**Alternative Tyre Allocation**:
The 2023 trial Tyre Allocation of 11 sets (4 Soft, 4 Medium, 3 Hard) instead of 13, with a fixed Compound for each qualifying part. Used only at the 2023 Hungarian and Italian Grands Prix.
_Avoid_: ATA (fine in speech), reduced allocation

**Degradation**:
The lap time a Compound loses per lap as it wears. A harder Compound wears no faster than a softer one: each team's Degradation is ordered Soft ≥ Medium ≥ Hard.
_Avoid_: deg (fine in speech), tyre wear, drop-off

**Compound Pace**:
How much faster a fresh Tyre Set of a Compound laps than a fresh Hard at the same circuit and fuel load, in seconds per lap. The Hard's Compound Pace is 0; a softer Compound is never slower than a harder one.
_Avoid_: compound delta, tyre offset, grip advantage

**Long Run**:
A practice Stint of consistently timed consecutive laps at race pace on a heavy fuel load, used to measure Degradation. On sprint weekends, sprint race Stints also count as Long Runs.
_Avoid_: race sim, race run

**Historical Degradation**:
A circuit's field-level Degradation per dry Compound, estimated from previous seasons' race Stints at that circuit (same Regulation Era only, recent seasons weighted more, never the race being predicted). Used when no team ran a Compound in practice this weekend.
_Avoid_: history rate, past-season deg

**Push Lap**:
A single flat-out lap in practice, recognisable as a fast lap between slower preparation and cool-down laps. Several Push Laps may be done on one Tyre Set. Push Laps are not part of a Long Run.
_Avoid_: quali sim, hot lap, flying lap

**In-lap**:
The lap on which a driver enters the pits, the last lap of a Stint. It is slow, so it is left out of Degradation fits and measured separately as part of Pit Loss. The first lap of the next Stint, leaving the pits, is the **Out-lap** and is treated the same way.
_Avoid_: pit lap, box lap

**Pit Loss**:
The race time a driver loses by making one pit stop at a given circuit, compared with staying out.
_Avoid_: pit delta (fine in speech), stop time

**Simulated Race Time**:
The estimated total time for a driver to complete a race on a given Candidate Strategy.
_Avoid_: predicted time, race sim

### Predictions

**Candidate Strategy**:
One Strategy that a driver could plausibly be on, considered as an option when predicting.
_Avoid_: option, scenario

**Mirrored Strategy**:
A Candidate Strategy with the same Compounds as another, in a different order (M → H and H → M; H → H → M and M → H → H). Simulated Race Time doesn't depend on Compound order, so Mirrored Strategies always tie and share top-1 credit, until Circuit Tendency separates them.
_Avoid_: reversed strategy, mirror pair

**Strategy Prediction**:
A ranked set of Candidate Strategies for one driver, each with a probability.
_Avoid_: forecast, guess

**Pre-race Prediction**:
A Strategy Prediction made after practice and qualifying, before the race starts.

**Live Prediction**:
A Strategy Prediction made during the race, updated as laps are completed.
_Avoid_: in-race forecast

**Plausible**:
Describes a Candidate Strategy that is legal, runnable with the driver's Remaining Sets, and within a margin (the Plausible margin) of the driver's fastest Simulated Race Time. A Strategy Prediction contains only Plausible Candidate Strategies.

### History

**Regulation Era**:
A run of seasons raced under one set of technical regulations: 2022–2025 is one era, and 2026 starts a new one. Historical information is only drawn from races in the same Regulation Era as the race being predicted.
_Avoid_: rules era, generation

**Circuit Alias**:
One of the names a data source has used for the same physical circuit in different seasons, such as Marina Bay and Singapore, Monaco and Monte Carlo, Miami and Miami Gardens, or Yas Island and Yas Marina. Past races are looked up under every Circuit Alias, and each past race counts once in Pit Loss and Historical Degradation, however many aliases find it.
_Avoid_: venue rename, location alias

**Circuit Tendency**:
How often each stop count and Compound sequence has been run at a circuit in past Dry Races, with recent seasons counting more.

**Team Tendency**:
How conservative or aggressive a team's strategy choices have been compared with the rest of the field.

**Situational Tendency**:
How strategy choices shift with a driver's circumstances, such as starting position.

### Evaluation

**Backtest**:
Running Strategy Predictions on past races and scoring them against the Strategies drivers actually ran.

**Excluded Race**:
A race weekend in a Backtest's scope that produced no scores, because it was refused (not a Dry Race), failed, its data couldn't be loaded, or its data couldn't be fetched (FastF1's rate limit still hit after waiting, or a network error on the race, a session or a past race it reads), or, in an Offline Run, it was never downloaded. Every Excluded Race is listed with its reason, and a fetch failure and a race that wasn't downloaded are each distinct from a genuine data-unavailable failure.
_Avoid_: skipped race, failed race

**Cancelled Race**:
A round on the calendar that was called off and never took place (2023 Emilia Romagna). It is not a race weekend, so it is not an Excluded Race: it is left out of season listings and never read as history for a later race at the circuit.
_Avoid_: skipped race, missing race

**Data Quality Warning**:
A note on a scored race in a Backtest Result saying where its data was incomplete, why, and what was done about it: a practice, sprint or qualifying session that couldn't be loaded, a past season at the circuit that gave no usable samples (such as 2018–2020, which the timing archive refuses), source rows dropped because a field was empty, or, in an Offline Run, a past race or session that was never downloaded. The race is still scored; a race whose data can't be used at all, or couldn't be fetched, is an Excluded Race instead.
_Avoid_: history warning (it covers more than history), data error

**Held-out Season**:
The season whose races are never used to tune settings, so its Backtest score shows how the model does on races it wasn't tuned on. Currently 2025; the seasons used for tuning are the **Tuning Seasons** (2022–2024).
_Avoid_: test set, validation season

**Smoke Set**:
A small fixed set of races covering every path through the model, run as a quick Backtest to check nothing broke: Singapore, Monza, Baku, Austin and Jeddah 2024, plus Spain 2022 (the conventional, green pre-era Pit Loss path, ADR-0004 exception).
_Avoid_: sample races, quick set

**Offline Run**:
A Backtest, Smoke Set or single-race run that reads only data already downloaded and never contacts FastF1 or OpenF1. On the same saved data it gives the same results as an online run; anything it lacks is reported as not downloaded.
_Avoid_: cached run, cache-only mode

**Backtest Result**:
The saved record of one Backtest run: its scores overall and by breakdown, each scored race's Data Quality Warnings, its Excluded Races, the settings used and the code version.
_Avoid_: report, run output

**Strategy Match**:
A prediction whose stop count and Compound sequence equal what the driver actually ran. Stop Window accuracy is scored separately.
_Avoid_: hit, correct prediction

**Predicted-Strategy Stop**:
An actual pit stop by a scoreable driver whose actual Strategy is one of their Candidate Strategies. It is scored against that Candidate Strategy's Stop Window; a stop on any other Strategy can never be a Stop Window hit.
_Avoid_: matched stop, scoreable stop

**Neutralised Race**:
A race that had a Safety Car or Virtual Safety Car period. Scored separately in Backtests because its Deviations can't be predicted beforehand.
_Avoid_: SC race, disrupted race

**Replay**:
Feeding a past race to Live Predictions lap by lap, revealing only what was known at each lap.
_Avoid_: simulation, playback
