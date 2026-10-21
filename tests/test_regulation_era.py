"""Regulation Era boundaries, one source of truth (ADR-0004).

Fast tests: no internet, no FastF1."""

import pytest

from f1_strategy.regulation_era import era_of, era_start


def test_2022_through_2025_share_one_era() -> None:
    assert era_of(2022) == era_of(2025)
    assert era_start(2022) == 2022
    assert era_start(2025) == 2022


def test_2026_starts_a_new_era() -> None:
    assert era_start(2026) == 2026
    assert era_of(2026) != era_of(2025)


def test_pre_2022_is_before_the_first_known_era() -> None:
    with pytest.raises(ValueError, match="before the first known"):
        era_of(2021)
