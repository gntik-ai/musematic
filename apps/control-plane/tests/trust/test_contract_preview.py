from __future__ import annotations

from datetime import UTC, datetime
from platform.common.exceptions import ValidationError
from platform.trust.contract_service import ContractService
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest


class FakeContractRepository:
    def __init__(self, contract: SimpleNamespace) -> None:
        self.contract = contract

    async def get_contract(self, contract_id: UUID) -> SimpleNamespace | None:
        if contract_id == self.contract.id:
            return self.contract
        return None


class FakeMockLLMService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object] | None]] = []
        self.real_llm_calls_total = 0

    async def preview(
        self,
        input_text: str,
        context: dict[str, object] | None = None,
    ) -> SimpleNamespace:
        self.calls.append((input_text, context))
        return SimpleNamespace(
            output_text="mock contract decision",
            completion_metadata={"model": "mock-creator-preview-v1"},
            was_fallback=False,
        )


def _contract() -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        agent_id="finance:kyc-verifier",
        task_scope="Verify KYC packets",
        expected_outputs={"required": ["answer", "citations"]},
        quality_thresholds={"minimum_confidence": 0.7},
        time_constraint_seconds=None,
        cost_limit_tokens=10,
        escalation_conditions={"secret_detected": "terminate"},
        success_criteria={"requires_citation": True},
        enforcement_policy="escalate",
        is_archived=False,
        attached_revision_id=None,
        created_at=now,
        updated_at=now,
    )


def _service(
    contract: SimpleNamespace,
    mock_llm_service: FakeMockLLMService,
) -> ContractService:
    return ContractService(
        repository=FakeContractRepository(contract),  # type: ignore[arg-type]
        publisher=None,
        mock_llm_service=mock_llm_service,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_preview_contract_defaults_to_mock_llm_and_reports_clauses() -> None:
    contract = _contract()
    mock_llm = FakeMockLLMService()
    service = _service(contract, mock_llm)

    response = await service.preview_contract(
        contract.id,
        {"output": {"answer": "ok"}, "tokens": 12},
        workspace_id=contract.workspace_id,
    )

    assert response.mock_response == "mock contract decision"
    assert response.was_fallback is False
    assert "expected_outputs" in response.clauses_triggered
    assert response.clauses_violated == ["expected_outputs", "cost_limit_tokens"]
    assert response.final_action == "escalate"
    assert mock_llm.calls[0][1] == {
        "contract_id": str(contract.id),
        "agent_id": contract.agent_id,
    }
    assert mock_llm.real_llm_calls_total == 0


@pytest.mark.asyncio
async def test_preview_contract_rejects_real_llm_without_cost_acknowledgement() -> None:
    contract = _contract()
    service = _service(contract, FakeMockLLMService())

    with pytest.raises(ValidationError):
        await service.preview_contract(
            contract.id,
            {"output": {"answer": "ok"}},
            use_mock=False,
            cost_acknowledged=False,
            workspace_id=contract.workspace_id,
        )


@pytest.mark.asyncio
async def test_preview_contract_allows_explicit_real_llm_ack_without_mock_call() -> None:
    contract = _contract()
    mock_llm = FakeMockLLMService()
    service = _service(contract, mock_llm)

    response = await service.preview_contract(
        contract.id,
        {"output": {"answer": "ok", "citations": []}, "tokens": 1},
        use_mock=False,
        cost_acknowledged=True,
        workspace_id=contract.workspace_id,
    )

    assert response.mock_response is None
    assert response.was_fallback is False
    assert response.clauses_violated == []
    assert response.final_action == "continue"
    assert mock_llm.calls == []


@pytest.mark.asyncio
async def test_preview_contract_detects_secret_escalation_condition() -> None:
    contract = _contract()
    service = _service(contract, FakeMockLLMService())

    response = await service.preview_contract(
        contract.id,
        {"output": {"answer": "ok", "citations": []}, "note": "secret token leaked"},
        workspace_id=contract.workspace_id,
    )

    assert "escalation_conditions" in response.clauses_violated
    assert response.final_action == "escalate"
