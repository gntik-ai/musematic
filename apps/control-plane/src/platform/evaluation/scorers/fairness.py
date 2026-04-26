from __future__ import annotations

from platform.evaluation.exceptions import FairnessConfigError, InsufficientGroupsError
from platform.evaluation.schemas import (
    FairnessCase,
    FairnessMetricRow,
    FairnessScorerConfig,
    FairnessScorerResult,
)
from platform.evaluation.scorers.base import ScoreResult
from platform.evaluation.scorers.fairness_metrics import (
    calibration_brier,
    coverage_for,
    demographic_parity,
    equal_opportunity,
)
from typing import Any
from uuid import UUID, uuid4


class FairnessScorer:
    async def score(self, actual: str, expected: str, config: dict[str, Any]) -> ScoreResult:
        del actual, expected
        return ScoreResult(
            score=None,
            passed=None,
            rationale="Fairness is a suite-level scorer",
            extra={"evaluation_run_id": str(config.get("evaluation_run_id") or uuid4())},
        )

    async def score_suite(
        self,
        *,
        evaluation_run_id: UUID,
        agent_id: UUID,
        agent_revision_id: str,
        suite_id: UUID,
        cases: list[FairnessCase],
        config: FairnessScorerConfig,
        evaluated_by: UUID | None = None,
    ) -> FairnessScorerResult:
        rows: list[FairnessMetricRow] = []
        coverage: dict[str, Any] = {}
        notes: list[str] = []
        for attr in config.group_attributes:
            coverage[attr] = coverage_for(cases, attr, min_group_size=config.min_group_size)
            for metric in config.metrics:
                try:
                    per_group, spread = self._metric(metric, cases, attr, config)
                    rows.append(
                        FairnessMetricRow(
                            evaluation_run_id=evaluation_run_id,
                            agent_id=agent_id,
                            agent_revision_id=agent_revision_id,
                            suite_id=suite_id,
                            metric_name=metric,
                            group_attribute=attr,
                            per_group_scores=per_group,
                            spread=spread,
                            fairness_band=config.fairness_band,
                            passed=spread <= config.fairness_band,
                            coverage=coverage[attr],
                            evaluated_by=evaluated_by,
                        )
                    )
                except InsufficientGroupsError:
                    notes.append(f"{metric}:{attr}:insufficient_groups")
                except FairnessConfigError as exc:
                    notes.append(f"{metric}:{attr}:unsupported:{exc.message}")
        overall = bool(rows) and all(row.passed for row in rows)
        return FairnessScorerResult(
            evaluation_run_id=evaluation_run_id,
            rows=rows,
            overall_passed=overall,
            coverage=coverage,
            notes=notes,
        )

    @staticmethod
    def _metric(
        metric: str,
        cases: list[FairnessCase],
        attr: str,
        config: FairnessScorerConfig,
    ) -> tuple[dict[str, float], float]:
        if metric == "demographic_parity":
            return demographic_parity(
                cases,
                attr,
                predicted_positive_fn=lambda case: (
                    str(case.prediction or case.actual) == config.positive_class
                ),
                min_group_size=config.min_group_size,
            )
        if metric == "equal_opportunity":
            return equal_opportunity(
                cases,
                attr,
                positive_class=config.positive_class,
                min_group_size=config.min_group_size,
            )
        if metric == "calibration":
            return calibration_brier(
                cases,
                attr,
                positive_class=config.positive_class,
                min_group_size=config.min_group_size,
            )
        raise ValueError(f"Unsupported fairness metric: {metric}")
