from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from platform.analytics.schemas import (
    ConfidenceLevel,
    OptimizationRecommendation,
    RecommendationType,
)
from typing import Any


class RecommendationEngine:
    def generate(
        self,
        agent_metrics: list[dict[str, Any]],
        fleet_baselines: Mapping[str, float | None],
    ) -> list[OptimizationRecommendation]:
        recommendations: list[OptimizationRecommendation] = []
        grouped: dict[str, list[dict[str, Any]]] = {}
        for metric in agent_metrics:
            grouped.setdefault(str(metric["agent_fqn"]), []).append(metric)

        for metrics in grouped.values():
            model_switch = self._check_model_switch(metrics)
            if model_switch is not None:
                recommendations.append(model_switch)

            for metric in metrics:
                self_correction = self._check_self_correction_tuning(
                    metric,
                    float(fleet_baselines.get("avg_loops") or 0.0),
                )
                if self_correction is not None:
                    recommendations.append(self_correction)

                context_optimization = self._check_context_optimization(
                    metric,
                    float(fleet_baselines.get("p95_input_output_ratio") or 0.0),
                    float(fleet_baselines.get("median_quality") or 0.0),
                )
                if context_optimization is not None:
                    recommendations.append(context_optimization)

                underutilization = self._check_underutilization(metric)
                if underutilization is not None:
                    recommendations.append(underutilization)

        return recommendations

    def _check_model_switch(
        self,
        agent_rows: list[dict[str, Any]],
    ) -> OptimizationRecommendation | None:
        eligible_rows = [row for row in agent_rows if int(row.get("execution_count", 0)) >= 30]
        if len(eligible_rows) < 2:
            return None

        sorted_by_cost = sorted(
            eligible_rows,
            key=lambda row: float(row.get("avg_cost_per_execution") or 0.0),
        )
        cheapest = sorted_by_cost[0]
        current = sorted_by_cost[-1]
        if cheapest["model_id"] == current["model_id"]:
            return None

        cheapest_quality = float(cheapest.get("avg_quality_score") or 0.0)
        current_quality = float(current.get("avg_quality_score") or 0.0)
        if abs(current_quality - cheapest_quality) > 0.05:
            return None

        current_cost = float(current.get("avg_cost_per_execution") or 0.0)
        cheapest_cost = float(cheapest.get("avg_cost_per_execution") or 0.0)
        if current_cost <= cheapest_cost:
            return None

        data_points = min(
            int(current.get("execution_count", 0)),
            int(cheapest.get("execution_count", 0)),
        )
        estimated_savings = max(
            current_cost - cheapest_cost,
            0.0,
        ) * max(
            int(
                current.get("execution_count_last_30d")
                or current.get("execution_count", 0)
            ),
            1,
        )
        agent_fqn = str(current["agent_fqn"])
        return OptimizationRecommendation(
            recommendation_type=RecommendationType.MODEL_SWITCH,
            agent_fqn=agent_fqn,
            title=f"Switch to {cheapest['model_id']} for cost savings",
            description=(
                f"Based on {data_points} executions, {agent_fqn} achieves similar quality "
                f"({cheapest_quality:.2f} vs. {current_quality:.2f}) at lower cost."
            ),
            estimated_savings_usd_per_month=round(estimated_savings, 4),
            confidence=self._confidence(data_points),
            data_points=data_points,
            supporting_data={
                "current_model": str(current["model_id"]),
                "suggested_model": str(cheapest["model_id"]),
                "current_avg_quality": round(current_quality, 4),
                "suggested_avg_quality": round(cheapest_quality, 4),
                "current_avg_cost_per_execution": round(current_cost, 6),
                "suggested_avg_cost_per_execution": round(cheapest_cost, 6),
            },
        )

    def _check_self_correction_tuning(
        self,
        agent_metric: dict[str, Any],
        fleet_avg_loops: float,
    ) -> OptimizationRecommendation | None:
        execution_count = int(agent_metric.get("execution_count", 0))
        avg_loops = float(agent_metric.get("avg_self_correction_loops") or 0.0)
        if execution_count < 10 or fleet_avg_loops <= 0 or avg_loops <= fleet_avg_loops * 2.0:
            return None

        excess_ratio = avg_loops / fleet_avg_loops
        savings = float(agent_metric.get("avg_cost_per_execution") or 0.0) * execution_count * 0.2
        agent_fqn = str(agent_metric["agent_fqn"])
        return OptimizationRecommendation(
            recommendation_type=RecommendationType.SELF_CORRECTION_TUNING,
            agent_fqn=agent_fqn,
            title="High self-correction loop count",
            description=(
                f"{agent_fqn} averages {avg_loops:.2f} self-correction loops per execution, "
                f"{excess_ratio:.1f}x above the workspace average of {fleet_avg_loops:.2f}."
            ),
            estimated_savings_usd_per_month=round(savings, 4),
            confidence=self._confidence(execution_count),
            data_points=execution_count,
            supporting_data={
                "agent_avg_loops": round(avg_loops, 4),
                "workspace_avg_loops": round(fleet_avg_loops, 4),
                "excess_ratio": round(excess_ratio, 4),
                "cost_per_retry": round(
                    float(agent_metric.get("avg_cost_per_execution") or 0.0),
                    6,
                ),
            },
        )

    def _check_context_optimization(
        self,
        agent_metric: dict[str, Any],
        fleet_p95_ratio: float,
        fleet_median_quality: float,
    ) -> OptimizationRecommendation | None:
        execution_count = int(agent_metric.get("execution_count", 0))
        avg_input_tokens = float(agent_metric.get("avg_input_tokens") or 0.0)
        avg_output_tokens = float(agent_metric.get("avg_output_tokens") or 0.0)
        avg_quality = float(agent_metric.get("avg_quality_score") or 0.0)
        ratio = avg_input_tokens / max(avg_output_tokens, 1.0)
        if (
            execution_count < 20
            or fleet_p95_ratio <= 0
            or ratio <= fleet_p95_ratio
            or avg_quality >= fleet_median_quality
        ):
            return None

        savings = float(agent_metric.get("avg_cost_per_execution") or 0.0) * execution_count * 0.15
        agent_fqn = str(agent_metric["agent_fqn"])
        return OptimizationRecommendation(
            recommendation_type=RecommendationType.CONTEXT_OPTIMIZATION,
            agent_fqn=agent_fqn,
            title="Prompt context appears oversized",
            description=(
                f"{agent_fqn} shows an input/output token ratio of {ratio:.2f}, above the fleet "
                f"95th percentile of {fleet_p95_ratio:.2f}, while quality remains below median."
            ),
            estimated_savings_usd_per_month=round(savings, 4),
            confidence=self._confidence(execution_count),
            data_points=execution_count,
            supporting_data={
                "input_output_ratio": round(ratio, 4),
                "fleet_p95_input_output_ratio": round(fleet_p95_ratio, 4),
                "avg_quality_score": round(avg_quality, 4),
                "fleet_median_quality": round(fleet_median_quality, 4),
            },
        )

    def _check_underutilization(
        self,
        agent_metric: dict[str, Any],
    ) -> OptimizationRecommendation | None:
        execution_count_last_30d = int(agent_metric.get("execution_count_last_30d", 0))
        first_seen = agent_metric.get("first_seen")
        if not isinstance(first_seen, datetime):
            return None
        if first_seen.tzinfo is None:
            first_seen = first_seen.replace(tzinfo=UTC)
        age_days = (datetime.now(UTC) - first_seen).days
        if execution_count_last_30d >= 5 or age_days <= 7:
            return None

        data_points = int(agent_metric.get("execution_count", execution_count_last_30d))
        agent_fqn = str(agent_metric["agent_fqn"])
        return OptimizationRecommendation(
            recommendation_type=RecommendationType.UNDERUTILIZATION,
            agent_fqn=agent_fqn,
            title="Agent appears underutilized",
            description=(
                f"{agent_fqn} has only {execution_count_last_30d} executions in the last 30 days "
                f"despite existing for {age_days} days."
            ),
            estimated_savings_usd_per_month=0.0,
            confidence=self._confidence(max(data_points, 1)),
            data_points=max(data_points, 1),
            supporting_data={
                "execution_count_last_30d": execution_count_last_30d,
                "age_days": age_days,
            },
        )

    def _confidence(self, data_points: int) -> ConfidenceLevel:
        if data_points >= 100:
            return ConfidenceLevel.HIGH
        if data_points >= 30:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW
