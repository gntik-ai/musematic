from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.analytics.recommendation import RecommendationEngine
from platform.analytics.schemas import ConfidenceLevel, RecommendationType


def test_model_switch_recommendation_triggers_with_similar_quality() -> None:
    engine = RecommendationEngine()

    recommendations = engine.generate(
        [
            {
                "agent_fqn": "planner:daily",
                "model_id": "gpt-4o",
                "avg_cost_per_execution": 0.12,
                "avg_quality_score": 0.92,
                "execution_count": 120,
                "execution_count_last_30d": 100,
            },
            {
                "agent_fqn": "planner:daily",
                "model_id": "gemini-2.0-flash",
                "avg_cost_per_execution": 0.04,
                "avg_quality_score": 0.90,
                "execution_count": 115,
                "execution_count_last_30d": 100,
            },
        ],
        {
            "avg_loops": 1.0,
            "median_quality": 0.8,
            "p95_input_output_ratio": 5.0,
        },
    )

    model_switch = next(
        item
        for item in recommendations
        if item.recommendation_type == RecommendationType.MODEL_SWITCH
    )
    assert model_switch.estimated_savings_usd_per_month > 0
    assert model_switch.confidence == ConfidenceLevel.HIGH
    assert model_switch.supporting_data["suggested_model"] == "gemini-2.0-flash"


def test_model_switch_does_not_trigger_with_quality_gap_or_low_samples() -> None:
    engine = RecommendationEngine()

    quality_gap = engine._check_model_switch(
        [
            {
                "agent_fqn": "planner:daily",
                "model_id": "gpt-4o",
                "avg_cost_per_execution": 0.1,
                "avg_quality_score": 0.95,
                "execution_count": 30,
            },
            {
                "agent_fqn": "planner:daily",
                "model_id": "cheap-model",
                "avg_cost_per_execution": 0.01,
                "avg_quality_score": 0.80,
                "execution_count": 30,
            },
        ]
    )
    low_samples = engine._check_model_switch(
        [
            {
                "agent_fqn": "planner:daily",
                "model_id": "gpt-4o",
                "avg_cost_per_execution": 0.1,
                "avg_quality_score": 0.90,
                "execution_count": 20,
            },
            {
                "agent_fqn": "planner:daily",
                "model_id": "cheap-model",
                "avg_cost_per_execution": 0.01,
                "avg_quality_score": 0.89,
                "execution_count": 20,
            },
        ]
    )

    assert quality_gap is None
    assert low_samples is None


def test_self_correction_and_context_rules_trigger_only_past_thresholds() -> None:
    engine = RecommendationEngine()

    self_correction = engine._check_self_correction_tuning(
        {
            "agent_fqn": "writer:review",
            "execution_count": 40,
            "avg_self_correction_loops": 4.2,
            "avg_cost_per_execution": 0.08,
        },
        2.0,
    )
    not_enough = engine._check_self_correction_tuning(
        {
            "agent_fqn": "writer:review",
            "execution_count": 40,
            "avg_self_correction_loops": 3.0,
            "avg_cost_per_execution": 0.08,
        },
        2.0,
    )
    context = engine._check_context_optimization(
        {
            "agent_fqn": "research:summary",
            "execution_count": 50,
            "avg_input_tokens": 1800,
            "avg_output_tokens": 100,
            "avg_quality_score": 0.68,
            "avg_cost_per_execution": 0.05,
        },
        10.0,
        0.75,
    )

    assert self_correction is not None
    assert self_correction.recommendation_type == RecommendationType.SELF_CORRECTION_TUNING
    assert not_enough is None
    assert context is not None
    assert context.recommendation_type == RecommendationType.CONTEXT_OPTIMIZATION


def test_underutilization_and_confidence_levels() -> None:
    engine = RecommendationEngine()

    recommendation = engine._check_underutilization(
        {
            "agent_fqn": "ops:nightly",
            "execution_count": 12,
            "execution_count_last_30d": 2,
            "first_seen": datetime.now(UTC) - timedelta(days=20),
        }
    )

    assert recommendation is not None
    assert recommendation.recommendation_type == RecommendationType.UNDERUTILIZATION
    assert engine._confidence(100) == ConfidenceLevel.HIGH
    assert engine._confidence(30) == ConfidenceLevel.MEDIUM
    assert engine._confidence(10) == ConfidenceLevel.LOW


def test_generate_aggregates_multiple_recommendation_types() -> None:
    engine = RecommendationEngine()

    recommendations = engine.generate(
        [
            {
                "agent_fqn": "writer:review",
                "model_id": "gpt-4o",
                "avg_cost_per_execution": 0.08,
                "avg_quality_score": 0.70,
                "execution_count": 50,
                "avg_self_correction_loops": 4.5,
                "avg_input_tokens": 1500,
                "avg_output_tokens": 100,
                "execution_count_last_30d": 2,
                "first_seen": datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30),
            }
        ],
        {
            "avg_loops": 1.5,
            "median_quality": 0.8,
            "p95_input_output_ratio": 10.0,
        },
    )

    assert {item.recommendation_type for item in recommendations} == {
        RecommendationType.SELF_CORRECTION_TUNING,
        RecommendationType.CONTEXT_OPTIMIZATION,
        RecommendationType.UNDERUTILIZATION,
    }


def test_recommendation_engine_handles_same_model_and_recent_agents() -> None:
    engine = RecommendationEngine()

    assert (
        engine._check_model_switch(
            [
                {
                    "agent_fqn": "planner:daily",
                    "model_id": "gpt-4o",
                    "avg_cost_per_execution": 0.05,
                    "avg_quality_score": 0.9,
                    "execution_count": 30,
                },
                {
                    "agent_fqn": "planner:daily",
                    "model_id": "gpt-4o",
                    "avg_cost_per_execution": 0.05,
                    "avg_quality_score": 0.9,
                    "execution_count": 30,
                },
            ]
        )
        is None
    )
    assert (
        engine._check_underutilization(
            {
                "agent_fqn": "planner:daily",
                "execution_count_last_30d": 10,
                "first_seen": datetime.now(UTC),
            }
        )
        is None
    )
