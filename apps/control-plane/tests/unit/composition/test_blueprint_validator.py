from __future__ import annotations

from platform.composition.models import AgentBlueprint, FleetBlueprint
from platform.composition.validation.validator import BlueprintValidator
from types import SimpleNamespace
from uuid import uuid4

import pytest


class Registry:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def get_available_tools(self, workspace_id):
        if self.fail:
            raise RuntimeError("down")
        return [
            SimpleNamespace(name="browser", capability_description="browse", is_accessible=True),
            SimpleNamespace(name="missing", is_accessible=False),
        ]

    async def get_available_models(self, workspace_id):
        if self.fail:
            raise RuntimeError("down")
        return [SimpleNamespace(identifier="gpt-test", is_accessible=True)]


class Connector:
    def __init__(self, *, fail: bool = False, configured: bool = True) -> None:
        self.fail = fail
        self.configured = configured

    async def check_connector_status(self, connector_name, workspace_id):
        if self.fail:
            raise RuntimeError("down")
        return {"configured": self.configured, "operational": self.configured}


class Policy:
    def __init__(self, *, fail: bool = False, passed: bool = True) -> None:
        self.fail = fail
        self.passed = passed

    async def evaluate_conformance(self, agent_fqn, revision_id, workspace_id):
        if self.fail:
            raise RuntimeError("down")
        return {"passed": self.passed, "violations": [{"policy_id": "p1"}]}


def _agent() -> AgentBlueprint:
    return AgentBlueprint(
        request_id=uuid4(),
        workspace_id=uuid4(),
        version=1,
        model_config={"model_id": "gpt-test"},
        tool_selections=[{"tool_name": "browser"}],
        connector_suggestions=[{"connector_name": "slack"}],
        policy_recommendations=[{"policy_id": "p1"}],
        context_profile={},
        maturity_estimate="developing",
        maturity_reasoning="ok",
        confidence_score=0.9,
        low_confidence=False,
        follow_up_questions=[],
        llm_reasoning_summary="",
        alternatives_considered=[],
    )


def _fleet(cycle: bool = False) -> FleetBlueprint:
    delegation = [{"from_role": "fetch", "to_role": "transform"}]
    escalation = [{"from_role": "transform", "to_role": "fetch" if cycle else "report"}]
    return FleetBlueprint(
        request_id=uuid4(),
        workspace_id=uuid4(),
        version=1,
        topology_type="sequential",
        member_count=2,
        member_roles=[
            {
                "role_name": "fetch",
                "purpose": "fetch",
                "agent_blueprint_inline": {
                    "model_config": {"model_id": "gpt-test"},
                    "tool_selections": [{"tool_name": "browser"}],
                    "connector_suggestions": [{"connector_name": "slack"}],
                    "policy_recommendations": [{"policy_id": "p1"}],
                },
            }
        ],
        orchestration_rules=[],
        delegation_rules=delegation,
        escalation_rules=escalation,
        confidence_score=0.8,
        low_confidence=False,
        follow_up_questions=[],
        llm_reasoning_summary="",
        alternatives_considered=[],
        single_agent_suggestion=False,
    )


@pytest.mark.asyncio
async def test_validate_agent_all_pass() -> None:
    validator = BlueprintValidator(
        registry_service=Registry(),
        connector_service=Connector(),
        policy_service=Policy(),
    )

    result = await validator.validate_agent(_agent(), uuid4())

    assert result["overall_valid"] is True
    assert result["cycle_check"] is None
    assert result["tools_check"].passed is True


@pytest.mark.asyncio
async def test_validate_agent_reports_tool_model_connector_and_policy_failures() -> None:
    agent = _agent()
    agent.tool_selections = [{"tool_name": "missing"}]
    agent.model_config = {"model_id": "unknown-model"}
    validator = BlueprintValidator(
        registry_service=Registry(),
        connector_service=Connector(configured=False),
        policy_service=Policy(passed=False),
    )

    result = await validator.validate_agent(agent, uuid4())

    assert result["overall_valid"] is False
    assert result["tools_check"].passed is False
    assert result["model_check"].passed is False
    assert result["connectors_check"].passed is False
    assert result["policy_check"].passed is False


@pytest.mark.asyncio
async def test_validate_fleet_detects_cycles() -> None:
    validator = BlueprintValidator(
        registry_service=Registry(),
        connector_service=Connector(),
        policy_service=Policy(),
    )

    result = await validator.validate_fleet(_fleet(cycle=True), uuid4())

    assert result["overall_valid"] is False
    assert result["cycle_check"].passed is False
    assert result["cycle_check"].details["cycles_found"][0]["path"] == [
        "fetch",
        "transform",
        "fetch",
    ]


@pytest.mark.asyncio
async def test_validate_degrades_when_services_are_unavailable() -> None:
    validator = BlueprintValidator(
        registry_service=Registry(fail=True),
        connector_service=Connector(fail=True),
        policy_service=Policy(fail=True),
    )

    result = await validator.validate_agent(_agent(), uuid4())

    assert result["overall_valid"] is False
    assert result["tools_check"].status == "validation_unavailable"
    assert result["model_check"].status == "validation_unavailable"
    assert result["connectors_check"].status == "validation_unavailable"
    assert result["policy_check"].status == "validation_unavailable"
