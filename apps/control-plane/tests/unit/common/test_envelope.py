from __future__ import annotations

from platform.common.events.envelope import CorrelationContext
from uuid import uuid4


def test_correlation_context_with_agent_fqn() -> None:
    context = CorrelationContext(
        correlation_id=uuid4(),
        workspace_id=uuid4(),
        agent_fqn="finance-ops:kyc-verifier",
    )

    payload = context.model_dump(mode="json")

    assert payload["agent_fqn"] == "finance-ops:kyc-verifier"


def test_correlation_context_without_agent_fqn() -> None:
    context = CorrelationContext(correlation_id=uuid4())

    assert context.agent_fqn is None


def test_correlation_context_backwards_compatible() -> None:
    legacy_payload = {
        "correlation_id": str(uuid4()),
        "workspace_id": str(uuid4()),
    }

    context = CorrelationContext.model_validate(legacy_payload)

    assert context.agent_fqn is None
