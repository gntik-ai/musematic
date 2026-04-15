from __future__ import annotations

from platform.agentops.regression.statistics import StatisticalComparator

import numpy as np
import pytest


@pytest.mark.parametrize("seed", [7, 42])
def test_statistical_comparator_selects_welch_for_large_normal_samples(seed: int) -> None:
    rng = np.random.default_rng(seed)
    sample_a = rng.normal(loc=0.92, scale=0.03, size=50).tolist()
    sample_b = rng.normal(loc=0.74, scale=0.03, size=50).tolist()

    result = StatisticalComparator.compare(sample_a, sample_b, alpha=0.05)

    assert result.test_type == "welch_t_test"
    assert result.p_value < 0.05
    assert result.significant is True
    assert result.effect_size > 1.0


def test_statistical_comparator_selects_mann_whitney_for_small_samples() -> None:
    rng = np.random.default_rng(9)
    sample_a = rng.exponential(scale=0.8, size=15).tolist()
    sample_b = rng.exponential(scale=1.6, size=15).tolist()

    result = StatisticalComparator.compare(sample_a, sample_b, alpha=0.05)

    assert result.test_type == "mann_whitney_u"
    assert result.significant is True
    assert result.p_value < 0.05
    assert abs(result.effect_size) > 0.1


def test_statistical_comparator_marks_shifted_normal_samples_as_significant() -> None:
    rng = np.random.default_rng(123)
    sample_a = rng.normal(loc=0.90, scale=0.02, size=60).tolist()
    sample_b = rng.normal(loc=0.70, scale=0.02, size=60).tolist()

    result = StatisticalComparator.compare(sample_a, sample_b, alpha=0.05)

    assert result.significant is True
    assert result.p_value < 0.001


def test_statistical_comparator_marks_similar_samples_as_not_significant() -> None:
    rng = np.random.default_rng(456)
    sample_a = rng.normal(loc=0.83, scale=0.03, size=60).tolist()
    sample_b = rng.normal(loc=0.831, scale=0.03, size=60).tolist()

    result = StatisticalComparator.compare(sample_a, sample_b, alpha=0.05)

    assert result.significant is False
    assert result.p_value >= 0.05


def test_statistical_comparator_computes_effect_size_for_mann_whitney() -> None:
    sample_a = [1, 2, 3, 4, 5, 6, 7, 8]
    sample_b = [8, 9, 10, 11, 12, 13, 14, 15]

    result = StatisticalComparator.compare(sample_a, sample_b, alpha=0.05)

    assert result.test_type == "mann_whitney_u"
    assert result.effect_size > 0.8
