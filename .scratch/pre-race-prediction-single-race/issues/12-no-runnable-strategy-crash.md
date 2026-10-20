# 12: `predict()` crashes when a driver has no runnable Strategy

**What to build:** Handle a driver whose Remaining Sets rule out every legal Strategy. Today `_predict_driver` indexes an empty list and raises `IndexError`.

**Blocked by:** None

**Status:** needs-triage

- [ ] A driver with no runnable Strategy doesn't crash the prediction for the rest of the field
- [ ] What the driver gets instead is decided and tested through `predict()` (for example, fall back to counting used sets, or report that driver as unpredictable)
- [ ] Baku 2024 can be predicted

## Comments

**From ticket 08 (2026-10-20).** Baku 2024: Alonso's new-sets-only Remaining Sets (ADR-0002) come out as S=0, M=1, H=0, so no Strategy using two dry Compounds survives. He raced on sets saved from practice, which ADR-0002 deliberately doesn't count. ADR-0002 claimed the understatement only shrinks the Candidate set; here it empties it, which may be worth revisiting in that ADR.
