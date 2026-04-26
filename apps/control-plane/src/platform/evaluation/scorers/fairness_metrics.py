from __future__ import annotations

from collections.abc import Callable, Iterable
from platform.evaluation.exceptions import FairnessConfigError, InsufficientGroupsError
from typing import Any

import numpy as np

Case = Any


def demographic_parity(
    cases: Iterable[Case],
    attr: str,
    *,
    predicted_positive_fn: Callable[[Case], bool],
    min_group_size: int,
) -> tuple[dict[str, float], float]:
    groups = _groups(cases, attr, min_group_size=min_group_size)
    rates = {
        group: float(np.mean([1.0 if predicted_positive_fn(case) else 0.0 for case in items]))
        for group, items in groups.items()
    }
    return rates, _spread(rates)


def equal_opportunity(
    cases: Iterable[Case],
    attr: str,
    *,
    positive_class: str,
    min_group_size: int,
) -> tuple[dict[str, float], float]:
    groups = _groups(
        [case for case in cases if _label(case) == positive_class],
        attr,
        min_group_size=min_group_size,
    )
    rates = {
        group: float(
            np.mean([1.0 if _prediction(case) == positive_class else 0.0 for case in items])
        )
        for group, items in groups.items()
    }
    return rates, _spread(rates)


def calibration_brier(
    cases: Iterable[Case],
    attr: str,
    *,
    positive_class: str,
    min_group_size: int,
) -> tuple[dict[str, float], float]:
    groups = _groups(cases, attr, min_group_size=min_group_size)
    scores: dict[str, float] = {}
    for group, items in groups.items():
        values: list[float] = []
        for case in items:
            score = _score(case)
            if score is None:
                raise FairnessConfigError("calibration requires probabilistic score output")
            expected = 1.0 if _label(case) == positive_class else 0.0
            values.append((score - expected) ** 2)
        scores[group] = float(np.mean(values))
    return scores, _spread(scores)


def coverage_for(cases: Iterable[Case], attr: str, *, min_group_size: int) -> dict[str, Any]:
    raw: dict[str, int] = {}
    missing = 0
    for case in cases:
        value = _group_value(case, attr)
        if value is None:
            missing += 1
            continue
        raw[value] = raw.get(value, 0) + 1
    included = {group: count for group, count in raw.items() if count >= min_group_size}
    excluded = {group: count for group, count in raw.items() if count < min_group_size}
    return {
        "total": sum(raw.values()) + missing,
        "included": included,
        "excluded_below_min_size": excluded,
        "missing": missing,
    }


def _groups(cases: Iterable[Case], attr: str, *, min_group_size: int) -> dict[str, list[Case]]:
    groups: dict[str, list[Case]] = {}
    for case in cases:
        value = _group_value(case, attr)
        if value is None:
            continue
        groups.setdefault(value, []).append(case)
    groups = {group: items for group, items in groups.items() if len(items) >= min_group_size}
    if len(groups) < 2:
        raise InsufficientGroupsError(attr)
    return groups


def _spread(values: dict[str, float]) -> float:
    if not values:
        return 0.0
    return float(max(values.values()) - min(values.values()))


def _group_value(case: Case, attr: str) -> str | None:
    group_attributes = _get(case, "group_attributes", {})
    if isinstance(group_attributes, dict) and attr in group_attributes:
        return str(group_attributes[attr])
    value = _get(case, attr, None)
    return str(value) if value is not None else None


def _label(case: Case) -> str:
    value = _get(case, "label", _get(case, "expected", None))
    return str(value)


def _prediction(case: Case) -> str:
    value = _get(case, "prediction", _get(case, "actual", None))
    return str(value)


def _score(case: Case) -> float | None:
    value = _get(case, "score", None)
    return None if value is None else float(value)


def _get(case: Case, field: str, default: Any) -> Any:
    if isinstance(case, dict):
        return case.get(field, default)
    return getattr(case, field, default)
