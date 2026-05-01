from __future__ import annotations

from platform.common.exceptions import ValidationError
from platform.simulation.scenarios_service import SimulationScenariosService
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest


class _RegistryStub:
    def __init__(self, known_fqns: set[str]) -> None:
        self.known_fqns = known_fqns

    async def get_agent_by_fqn(self, fqn: str) -> object | None:
        return object() if fqn in self.known_fqns else None


class _SyncRegistryStub:
    def resolve_fqn(self, fqn: str) -> object | None:
        return object() if fqn == "registry:known" else None


class _WorkflowStub:
    def __init__(self, result: object | None) -> None:
        self.result = result

    async def get_workflow_template(self, workflow_template_id: object) -> object | None:
        del workflow_template_id
        return self.result


def _service(
    *,
    registry_service: object | None = None,
    workflow_service: object | None = None,
) -> SimulationScenariosService:
    return SimulationScenariosService(
        repository=object(),  # type: ignore[arg-type]
        runner=object(),  # type: ignore[arg-type]
        settings=SimpleNamespace(simulation=SimpleNamespace(max_duration_seconds=3600)),  # type: ignore[arg-type]
        registry_service=registry_service,
        workflow_service=workflow_service,
    )


def _valid_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "name": "Scenario",
        "agents_config": {"agents": ["registry:known"]},
        "workflow_template_id": None,
        "mock_set_config": {"llm": "mock"},
        "input_distribution": {"kind": "fixed", "value": "hello"},
        "twin_fidelity": {"tools": "mock", "data_source": "synthetic"},
        "success_criteria": [{"metric": "accuracy", "operator": ">=", "value": 0.9}],
        "run_schedule": None,
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize(
    ("values", "expected_code", "registry_service", "workflow_service"),
    [
        (
            _valid_values(mock_set_config={"api_key": "sk-test-secret-123456"}),
            "PLAINTEXT_SECRET",
            None,
            None,
        ),
        (
            _valid_values(input_distribution={"password": "pass-value-123456"}),
            "PLAINTEXT_SECRET",
            None,
            None,
        ),
        (
            _valid_values(agents_config={"plaintext_secret": "agent-secret-123456"}),
            "PLAINTEXT_SECRET",
            None,
            None,
        ),
        (
            _valid_values(twin_fidelity={"token": "twin-token-123456"}),
            "PLAINTEXT_SECRET",
            None,
            None,
        ),
        (
            _valid_values(success_criteria=[{"secret": "aaaaaaaa"}]),
            "PLAINTEXT_SECRET",
            None,
            None,
        ),
        (
            _valid_values(run_schedule={"api_key": "aaaaaaaa"}),
            "PLAINTEXT_SECRET",
            None,
            None,
        ),
        (_valid_values(success_criteria=[]), "EMPTY_SUCCESS_CRITERIA", None, None),
        (_valid_values(success_criteria={}), "EMPTY_SUCCESS_CRITERIA", None, None),
        (_valid_values(success_criteria=None), "EMPTY_SUCCESS_CRITERIA", None, None),
        (
            _valid_values(
                twin_fidelity={
                    "mode": "real:production-data",
                    "tools": "mock:tool-gateway",
                }
            ),
            "FORBIDDEN_TWIN_COMBO",
            None,
            None,
        ),
        (
            _valid_values(
                twin_fidelity={
                    "data_source": "production",
                    "tool_gateway": "mock",
                }
            ),
            "FORBIDDEN_TWIN_COMBO",
            None,
            None,
        ),
        (
            _valid_values(agents_config={"agents": ["registry:missing"]}),
            "UNKNOWN_AGENT_FQN",
            _RegistryStub({"registry:known"}),
            None,
        ),
        (
            _valid_values(agents_config={"agents": [{"fqn": "registry:missing"}]}),
            "UNKNOWN_AGENT_FQN",
            _RegistryStub({"registry:known"}),
            None,
        ),
        (
            _valid_values(workflow_template_id=uuid4()),
            "WORKFLOW_TEMPLATE_NOT_FOUND",
            None,
            _WorkflowStub(None),
        ),
        (
            _valid_values(workflow_template_id=uuid4()),
            "WORKFLOW_TEMPLATE_NOT_APPROVED",
            None,
            _WorkflowStub(SimpleNamespace(approval_status="draft")),
        ),
    ],
)
@pytest.mark.asyncio
async def test_scenario_validation_rejects_invalid_configs(
    values: dict[str, Any],
    expected_code: str,
    registry_service: object | None,
    workflow_service: object | None,
) -> None:
    service = _service(registry_service=registry_service, workflow_service=workflow_service)

    with pytest.raises(ValidationError) as exc_info:
        await service._validate_payload(values)

    assert exc_info.value.code == expected_code


@pytest.mark.asyncio
async def test_scenario_validation_accepts_known_agents_and_approved_workflow() -> None:
    service = _service(
        registry_service=_SyncRegistryStub(),
        workflow_service=_WorkflowStub(SimpleNamespace(approval_status="approved")),
    )

    await service._validate_payload(_valid_values(workflow_template_id=uuid4()))
