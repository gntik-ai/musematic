from __future__ import annotations

from decimal import Decimal
from platform.analytics.consumer import AnalyticsPipelineConsumer
from platform.common.config import PlatformSettings
from uuid import uuid4

from tests.analytics_support import ClickHouseClientStub, build_cost_model, build_envelope


def _consumer() -> AnalyticsPipelineConsumer:
    return AnalyticsPipelineConsumer(
        settings=PlatformSettings(),
        clickhouse_client=ClickHouseClientStub(),  # type: ignore[arg-type]
    )


def test_compute_cost_uses_token_and_duration_pricing() -> None:
    consumer = _consumer()
    consumer._pricing_cache["gpt-4o"] = build_cost_model(per_second_cost="0.50")

    cost = consumer._compute_cost(1000, 2000, 4000, "gpt-4o")

    expected = float(
        (
            Decimal(1000) * Decimal("0.0000025")
            + Decimal(2000) * Decimal("0.0000100")
            + Decimal("4") * Decimal("0.50")
        ).quantize(Decimal("0.0000000001"))
    )
    assert cost == expected


def test_compute_cost_returns_zero_when_model_is_missing() -> None:
    consumer = _consumer()

    assert consumer._compute_cost(100, 100, 1000, "unknown-model") == 0.0


def test_extract_usage_event_infers_provider_and_agent_fqn() -> None:
    consumer = _consumer()
    envelope = build_envelope(
        workspace_id=uuid4(),
        payload={
            "agent_namespace": "planner",
            "agent_name": "daily",
            "model_id": "gpt-4o",
            "input_tokens": 100,
            "output_tokens": 40,
            "execution_duration_ms": 250,
            "self_correction_loops": 2,
            "reasoning_tokens": 5,
        },
    )

    row = consumer._extract_usage_event(envelope)

    assert row is not None
    assert row["agent_fqn"] == "planner:daily"
    assert row["provider"] == "openai"
    assert row["execution_duration_ms"] == 250


def test_extract_usage_event_requires_workspace_agent_and_model() -> None:
    consumer = _consumer()

    missing_workspace = consumer._extract_usage_event(
        build_envelope(payload={"agent_fqn": "planner:daily", "model_id": "gpt-4o"})
    )
    missing_agent = consumer._extract_usage_event(
        build_envelope(workspace_id=uuid4(), payload={"model_id": "gpt-4o"})
    )
    missing_model = consumer._extract_usage_event(
        build_envelope(workspace_id=uuid4(), payload={"agent_fqn": "planner:daily"})
    )

    assert missing_workspace is None
    assert missing_agent is None
    assert missing_model is None


def test_extract_quality_event_parses_payload_and_defaults_eval_suite() -> None:
    consumer = _consumer()
    execution_id = uuid4()
    envelope = build_envelope(
        event_type="evaluation.completed",
        workspace_id=uuid4(),
        execution_id=execution_id,
        payload={
            "agent_fqn": "planner:daily",
            "model_id": "gpt-4o",
            "quality_score": 0.86,
        },
    )

    row = consumer._extract_quality_event(envelope)

    assert row is not None
    assert row["execution_id"] == execution_id
    assert row["quality_score"] == 0.86
    assert str(row["eval_suite_id"]) == "00000000-0000-0000-0000-000000000000"


def test_extract_quality_event_requires_complete_payload() -> None:
    consumer = _consumer()

    row = consumer._extract_quality_event(
        build_envelope(
            workspace_id=uuid4(),
            payload={"agent_fqn": "planner:daily", "quality_score": 0.9},
        )
    )

    assert row is None
