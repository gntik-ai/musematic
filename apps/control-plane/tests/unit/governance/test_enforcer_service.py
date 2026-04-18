from __future__ import annotations

from datetime import UTC, datetime
from platform.governance.models import ActionType, EnforcementAction, GovernanceVerdict, VerdictType
from platform.governance.services.enforcer_service import EnforcerService
from platform.governance.services.pipeline_config import ChainConfig
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tests.auth_support import RecordingProducer


class RepoStub:
    def __init__(self, existing: EnforcementAction | None = None) -> None:
        self.existing = existing
        self.created: list[EnforcementAction] = []

    async def get_enforcement_action_for_verdict(self, verdict_id):
        del verdict_id
        return self.existing

    async def create_enforcement_action(self, action: EnforcementAction) -> EnforcementAction:
        action.id = uuid4()
        action.created_at = datetime.now(UTC)
        action.updated_at = action.created_at
        self.created.append(action)
        self.existing = action
        return action


class CertificationServiceStub:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str, object]] = []

    async def revoke(self, certification_id, reason, actor_id):
        self.calls.append((certification_id, reason, actor_id))
        return SimpleNamespace(id=certification_id)


def _verdict(verdict_type: VerdictType = VerdictType.VIOLATION, **evidence) -> GovernanceVerdict:
    verdict = GovernanceVerdict(
        id=uuid4(),
        judge_agent_fqn="platform:judge",
        verdict_type=verdict_type,
        policy_id=uuid4(),
        evidence={"target_agent_fqn": "finance:agent", **evidence},
        rationale="policy matched",
        recommended_action=None,
        source_event_id=uuid4(),
        fleet_id=uuid4(),
        workspace_id=uuid4(),
    )
    verdict.created_at = datetime.now(UTC)
    verdict.updated_at = verdict.created_at
    return verdict


def _chain(mapping: dict[str, str]) -> ChainConfig:
    return ChainConfig(
        observer_fqns=["platform:observer"],
        judge_fqns=["platform:judge"],
        enforcer_fqns=["platform:enforcer"],
        policy_binding_ids=[],
        verdict_to_action_mapping=mapping,
        scope="fleet",
    )


@pytest.mark.asyncio
async def test_process_verdict_persists_block_action() -> None:
    repo = RepoStub()
    producer = RecordingProducer()
    service = EnforcerService(repository=repo, producer=producer, certification_service=None)

    action = await service.process_verdict(_verdict(), _chain({"VIOLATION": "block"}))

    assert action.action_type is ActionType.block
    assert action.target_agent_fqn == "finance:agent"
    assert repo.created[0].outcome == {"blocked": True, "target_agent_fqn": "finance:agent"}
    assert producer.events[0]["event_type"] == "governance.enforcement.executed"


@pytest.mark.asyncio
async def test_process_verdict_persists_notify_action() -> None:
    repo = RepoStub()
    service = EnforcerService(repository=repo, producer=None, certification_service=None)

    action = await service.process_verdict(
        _verdict(VerdictType.WARNING),
        _chain({"WARNING": "notify"}),
    )

    assert action.action_type is ActionType.notify
    assert repo.created[0].outcome["notified"] is True


@pytest.mark.asyncio
async def test_process_verdict_revokes_certification() -> None:
    certification_id = uuid4()
    repo = RepoStub()
    certs = CertificationServiceStub()
    service = EnforcerService(repository=repo, producer=None, certification_service=certs)

    action = await service.process_verdict(
        _verdict(certification_id=certification_id),
        _chain({"VIOLATION": "revoke_cert"}),
    )

    assert action.action_type is ActionType.revoke_cert
    assert certs.calls[0][0] == certification_id
    assert repo.created[0].outcome["revoked"] is True


@pytest.mark.asyncio
async def test_process_verdict_defaults_to_log_and_continue() -> None:
    repo = RepoStub()
    service = EnforcerService(repository=repo, producer=None, certification_service=None)

    action = await service.process_verdict(_verdict(VerdictType.WARNING), _chain({}))

    assert action.action_type is ActionType.log_and_continue
    assert repo.created[0].outcome["unmapped_verdict_type"] == "WARNING"


@pytest.mark.asyncio
async def test_process_verdict_is_idempotent() -> None:
    existing = EnforcementAction(
        id=uuid4(),
        enforcer_agent_fqn="platform:enforcer",
        verdict_id=uuid4(),
        action_type=ActionType.block,
        target_agent_fqn="finance:agent",
        outcome={"blocked": True},
        workspace_id=uuid4(),
    )
    existing.created_at = datetime.now(UTC)
    existing.updated_at = existing.created_at
    repo = RepoStub(existing=existing)
    service = EnforcerService(repository=repo, producer=None, certification_service=None)
    verdict = _verdict()
    verdict.id = existing.verdict_id

    action = await service.process_verdict(verdict, _chain({"VIOLATION": "block"}))

    assert action is existing
    assert repo.created == []


@pytest.mark.asyncio
async def test_process_verdict_records_missing_target() -> None:
    repo = RepoStub()
    service = EnforcerService(repository=repo, producer=None, certification_service=None)

    action = await service.process_verdict(
        _verdict(target_agent_fqn=""),
        _chain({"VIOLATION": "block"}),
    )

    assert action.action_type is ActionType.block
    assert repo.created[0].outcome == {"error": "target_not_found", "target_agent_fqn": None}
