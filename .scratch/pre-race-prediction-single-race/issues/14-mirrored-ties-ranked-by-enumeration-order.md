# 14: The scorer counts mirrored ties as top-1 by enumeration order

**What to build:** Make Strategy Match fair when Candidate Strategies tie exactly. Mirrored Strategies (M → H and H → M) share the same probability (ticket 09 accepts the 50/50 split until Circuit Tendency), but `predict()` sorts stably over Strategies generated in S, M, H order. The softer-first mirror is always first, and the scorer counts it as the top-1 pick. The "50/50" is really "softer-first wins", which happens to match what most teams do and so inflates the "before" number.

**Blocked by:** None

**Status:** needs-triage

- [ ] Strategy Match handles equal-probability Candidate Strategies in a stated, order-independent way (for example, a tie counts as a 1/k match, or the summary reports top-1 with ties separately)
- [ ] Reordering how Strategies are enumerated doesn't change any score
- [ ] Tests go through `predict()` and `compare()`

## Comments

**From ticket 08 (2026-10-20).** Singapore 2024: both scored top-1 matches (VER, PIA), and all six among classified finishers, were M → H tied with H → M. Credited as half a match each, top-1 would be 1/7, not 2/7. Ties of 4–6 Candidate Strategies also occur (ticket 13), where top-3 is decided by enumeration order too. This should land before the "before" number is used against Circuit Tendency (ticket 09), or the gain from breaking mirrored ties will be understated.
