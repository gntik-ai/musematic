from __future__ import annotations

from platform.trust.exceptions import OJEConfigError
from platform.trust.models import OJEVerdictType
from platform.trust.schemas import JudgeVerdictEvent
from uuid import uuid4

import pytest

from tests.trust_support import build_oje_config_create, build_trust_bundle


@pytest.mark.asyncio
async def test_oje_pipeline_configure_list_get_and_deactivate() -> None:
    bundle = build_trust_bundle()
    bundle.registry_service.known_fqns.update({"observer:one", "judge:one", "enforcer:one"})

    created = await bundle.oje_service.configure_pipeline(build_oje_config_create())
    listed = await bundle.oje_service.list_pipeline_configs(created.workspace_id)
    fetched = await bundle.oje_service.get_pipeline_config(created.workspace_id, None)
    deactivated = await bundle.oje_service.deactivate_pipeline(created.id)

    assert created.id == fetched.id
    assert listed.total == 1
    assert deactivated.is_active is False


@pytest.mark.asyncio
async def test_oje_pipeline_processes_verdicts_and_executes_enforcement() -> None:
    bundle = build_trust_bundle()
    bundle.registry_service.known_fqns.update({"observer:one", "judge:one", "enforcer:one"})
    config = await bundle.oje_service.configure_pipeline(build_oje_config_create())

    violation = await bundle.oje_service.process_observation(
        {
            "judge_verdict": JudgeVerdictEvent(
                pipeline_config_id=str(config.id),
                observer_signal_id="signal-1",
                judge_fqn="judge:one",
                verdict=OJEVerdictType.violation,
                reasoning="bad behavior",
                policy_basis="agent-1",
                enforcer_action_taken="stop_runtime",
            ).model_dump(mode="json")
        },
        str(config.id),
    )

    bundle.interactions_service.verdict = {
        "pipeline_config_id": str(config.id),
        "observer_signal_id": "signal-2",
        "judge_fqn": "judge:one",
        "verdict": OJEVerdictType.escalate_to_human,
        "reasoning": "needs review",
        "policy_basis": "agent-1",
        "enforcer_action_taken": "escalate",
    }
    escalated = await bundle.oje_service.process_observation(
        {"signal_id": "signal-2"},
        str(config.id),
    )

    assert violation.verdict == OJEVerdictType.violation
    assert bundle.runtime_controller.stop_calls[-1]["reason"] == "bad behavior"
    assert escalated.verdict == OJEVerdictType.escalate_to_human
    assert bundle.producer.events[-1]["topic"] == "interaction.attention"
    assert len(bundle.repository.signals) == 2
    assert len(bundle.repository.proof_links) == 2


@pytest.mark.asyncio
async def test_oje_pipeline_handles_missing_configs_and_fallback_judges() -> None:
    bundle = build_trust_bundle()
    bundle.registry_service.known_fqns.update({"observer:one", "judge:one", "enforcer:one"})
    first = await bundle.oje_service.configure_pipeline(build_oje_config_create())
    second = await bundle.oje_service.configure_pipeline(build_oje_config_create())

    assert bundle.repository.oje_configs[0].is_active is False
    assert first.id == bundle.repository.oje_configs[0].id
    assert second.is_active is True

    with pytest.raises(OJEConfigError):
        await bundle.oje_service.get_pipeline_config("workspace-404", None)
    with pytest.raises(OJEConfigError):
        await bundle.oje_service.get_pipeline_config_by_id(uuid4())
    with pytest.raises(OJEConfigError):
        await bundle.oje_service.deactivate_pipeline(uuid4())
    with pytest.raises(OJEConfigError):
        await bundle.oje_service.process_observation({"signal_id": "missing"}, str(uuid4()))

    bundle.oje_service.interactions_service = None
    fallback = await bundle.oje_service._invoke_judges(
        bundle.repository.oje_configs[-1],
        {"signal_id": "signal-fallback"},
    )

    assert fallback.verdict == OJEVerdictType.compliant
    assert fallback.reasoning == "No judge integration configured"


@pytest.mark.asyncio
async def test_oje_pipeline_validates_fqns_and_uuid_helpers() -> None:
    bundle = build_trust_bundle()
    bundle.oje_service.registry_service = None
    await bundle.oje_service._ensure_fqn_exists(
        "00000000-0000-0000-0000-000000000001",
        "observer:one",
    )

    bundle.oje_service.registry_service = bundle.registry_service
    with pytest.raises(OJEConfigError):
        await bundle.oje_service._ensure_fqn_exists(
            "00000000-0000-0000-0000-000000000001",
            "missing:judge",
        )

    generated = uuid4()
    assert bundle.oje_service._uuid_from_text(generated) == generated
    assert bundle.oje_service._uuid_or_none("") is None
    assert bundle.oje_service._uuid_or_none("not-a-uuid") is None
