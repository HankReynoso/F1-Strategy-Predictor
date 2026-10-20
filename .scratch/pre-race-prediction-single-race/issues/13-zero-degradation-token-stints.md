# 13: Zero Degradation produces token Stints, degenerate Stop Windows and many-way ties

**What to build:** Stop zero-Degradation fits from turning into "stop on lap 1" Strategies. When a Compound's fitted Degradation is clamped to 0 and there's no Compound pace, a 1–2 lap Stint on another Compound costs nothing. The favourite becomes a token Stint, several Candidate Strategies tie exactly, and Stop Windows span almost the whole race.

**Blocked by:** None

**Status:** needs-triage

- [ ] A weekend where one team fits zero Degradation on a Compound doesn't produce top Candidate Strategies with a 1–2 lap Stint
- [ ] Stop Windows don't cover nearly the whole race when Degradation is flat
- [ ] Tests go through `predict()`

## Comments

**From ticket 08 (2026-10-20).** Singapore 2024: Mercedes (Medium and Hard), Ferrari (Hard), Williams (Medium), Sauber (Medium and Hard) and RB (Soft) all fit 0 after the clamp. Their top picks were things like "1-stop: S → M, Stop Window 1–2", tied 4–6 ways at 17–25%. Russell's actual M → H had a Stop Window of laps 1–61, which is the only Stop Window hit in the scored summary. The zeros also pull the field average down (field-average Hard 0.043 s/lap).

Possible directions: a minimum Stint length; Compound pace (spec Open questions; needs a glossary term via `/domain-modeling`); not clamping to exactly zero but shrinking noisy fits towards the field average; a floor on Degradation.
