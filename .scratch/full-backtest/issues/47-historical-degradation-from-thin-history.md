# 47: Historical Degradation from one or two short Stints is used as-is

**What to build:** Historical Degradation for a Compound is used as the Circuit History Degradation source whenever it exists, however few Stints it pools. Found in ticket 37's before/after record (2026-10-26): 2024 Australian Soft is 2.53 s/lap from a single 7-lap 2023 Stint, 2023 Miami Soft is −3.48 s/lap from one 4-lap Stint, and many Medium rates at Baku, Jeddah and Melbourne are negative after fuel correction. `HistoricalDegradation.stint_count` is recorded but `degradation.py` never checks it. Decide a minimum (Stint count, total laps, or both, as a setting tuned on the Tuning Seasons only), what to fall back to below it, and whether negative fuel-corrected rates should be clipped or treated as a sign the fuel effect is wrong for that circuit.

**Blocked by:** None (can start immediately); best judged after ticket 24's rerun

**Status:** needs-triage

**Category:** enhancement

- [ ] Historical Degradation below a minimum amount of history isn't used as Circuit History, and the fallback is recorded as a Degradation source
- [ ] The minimum is a setting, tuned on the Tuning Seasons only
- [ ] The choice about negative rates is recorded, with the counts of affected circuits and Compounds
- [ ] Backtest scores before and after are recorded

## Comments

Raised by the ticket 37 session (2026-10-26). See ticket 37's Implementation notes for the per-race numbers.
