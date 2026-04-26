from __future__ import annotations

from platform.evaluation.exceptions import FairnessConfigError, InsufficientGroupsError
from platform.evaluation.scorers.fairness_metrics import (
    calibration_brier,
    demographic_parity,
    equal_opportunity,
)

import pytest

CASES = [
    {
        "prediction": "positive",
        "label": "positive",
        "score": 0.9,
        "group_attributes": {"lang": "en"},
    },
    {
        "prediction": "negative",
        "label": "positive",
        "score": 0.4,
        "group_attributes": {"lang": "en"},
    },
    {
        "prediction": "positive",
        "label": "positive",
        "score": 0.8,
        "group_attributes": {"lang": "es"},
    },
    {
        "prediction": "positive",
        "label": "negative",
        "score": 0.7,
        "group_attributes": {"lang": "es"},
    },
]


def test_demographic_parity_is_deterministic() -> None:
    first = demographic_parity(
        CASES,
        "lang",
        predicted_positive_fn=lambda case: case["prediction"] == "positive",
        min_group_size=2,
    )
    second = demographic_parity(
        CASES,
        "lang",
        predicted_positive_fn=lambda case: case["prediction"] == "positive",
        min_group_size=2,
    )

    assert first == second
    assert first[0] == {"en": 0.5, "es": 1.0}
    assert first[1] == 0.5


def test_equal_opportunity() -> None:
    rates, spread = equal_opportunity(
        CASES,
        "lang",
        positive_class="positive",
        min_group_size=1,
    )

    assert rates == {"en": 0.5, "es": 1.0}
    assert spread == 0.5


def test_single_group_raises() -> None:
    with pytest.raises(InsufficientGroupsError):
        demographic_parity(
            [{"prediction": "positive", "group_attributes": {"lang": "en"}}],
            "lang",
            predicted_positive_fn=lambda case: True,
            min_group_size=1,
        )


def test_calibration_requires_scores() -> None:
    with pytest.raises(FairnessConfigError):
        calibration_brier(
            [
                {"prediction": "positive", "label": "positive", "group_attributes": {"lang": "en"}},
                {"prediction": "negative", "label": "negative", "group_attributes": {"lang": "es"}},
            ],
            "lang",
            positive_class="positive",
            min_group_size=1,
        )
