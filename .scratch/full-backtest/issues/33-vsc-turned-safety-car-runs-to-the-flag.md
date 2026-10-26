# 33: A VSC that turns into a Safety Car runs to the end of the race

**What to build:** `openf1_loader._neutralisation_periods` caps any SC or VSC with no end message at the race's last lap. In three cached races, a VSC was turned into a full Safety Car, so it never got a "VIRTUAL SAFETY CAR ENDING" message. Every lap from the VSC to the flag is then treated as neutralised:

- 2023 British (Silverstone, session 9126): VSC lap 33 then SC 33–38; read as VSC 33–52.
- 2024 Chinese (Shanghai, session 9673): VSC lap 22 then SC 23–26 and 27–31; read as VSC 22–56.
- 2024 Qatar (Lusail, session 9655): VSC lap 40 then SC 40–42; read as VSC 40–57.

Over-neutralising drops green laps from Pit Loss and Historical Degradation samples for every later race at those circuits, and moves nothing else. It doesn't invent laps, but it throws away most of a race. Decide the rule from the data, most likely "an SC deployment closes an open VSC on the same lap". Then check the other capped periods from the 2026-10-26 survey (Zandvoort 2023 rolling restart behind the SC after a red flag, VSC 64–72; last-lap VSCs at Melbourne 2024 and Baku 2024; Montréal 2025's SC 67–70, which is correct because the race finished behind the SC).

**Blocked by:** None (can start immediately)

**Status:** needs-triage

**Category:** bug

## Comments

Found during ticket 30, which fixed the red-flag-then-standing-restart case (São Paulo, Mexico City and Melbourne 2023) and left these alone because they are a different pattern. The real `race_control` rows for each are in `.cache/openf1`. Ticket 30's survey script approach (recompute every cached race's periods before and after, diff them) shows exactly which races a rule moves.

- [ ] Each capped period in the 2023–2025 cache has a recorded reading: fixed by a rule, or left capped with a reason
- [ ] Fixture tests from the real `race_control` rows for each changed pattern
- [ ] The before/after diff of every cached race's periods is recorded, and Smoke Set numbers are re-checked
