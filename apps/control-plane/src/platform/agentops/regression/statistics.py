from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass(slots=True)
class ComparisonResult:
    test_type: str
    statistic: float
    p_value: float
    effect_size: float
    significant: bool


class StatisticalComparator:
    @staticmethod
    def compare(
        sample_a: list[float],
        sample_b: list[float],
        alpha: float = 0.05,
    ) -> ComparisonResult:
        array_a = np.asarray(sample_a, dtype=float)
        array_b = np.asarray(sample_b, dtype=float)

        use_welch = False
        if len(array_a) >= 30 and len(array_b) >= 30:
            normality_a = stats.shapiro(array_a)
            normality_b = stats.shapiro(array_b)
            use_welch = normality_a.pvalue > alpha and normality_b.pvalue > alpha

        if use_welch:
            test = stats.ttest_ind(array_a, array_b, equal_var=False)
            effect_size = _cohens_d(array_a, array_b)
            return ComparisonResult(
                test_type="welch_t_test",
                statistic=float(test.statistic),
                p_value=float(test.pvalue),
                effect_size=effect_size,
                significant=bool(test.pvalue < alpha),
            )

        test = stats.mannwhitneyu(array_a, array_b, alternative="two-sided")
        effect_size = _rank_biserial(float(test.statistic), len(array_a), len(array_b))
        return ComparisonResult(
            test_type="mann_whitney_u",
            statistic=float(test.statistic),
            p_value=float(test.pvalue),
            effect_size=effect_size,
            significant=bool(test.pvalue < alpha),
        )


def _cohens_d(sample_a: np.ndarray, sample_b: np.ndarray) -> float:
    if sample_a.size < 2 or sample_b.size < 2:
        return 0.0
    variance_a = float(np.var(sample_a, ddof=1))
    variance_b = float(np.var(sample_b, ddof=1))
    pooled = np.sqrt((variance_a + variance_b) / 2.0)
    if float(pooled) == 0.0:
        return 0.0
    return float((np.mean(sample_a) - np.mean(sample_b)) / pooled)


def _rank_biserial(statistic: float, size_a: int, size_b: int) -> float:
    denominator = float(size_a * size_b)
    if denominator == 0.0:
        return 0.0
    return float(1.0 - ((2.0 * statistic) / denominator))
