from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.trust.exceptions import ContractConflictError
from platform.trust.models import (
    AgentContract,
    CertificationStatus,
    Certifier,
    ContractBreachEvent,
    EvidenceType,
    GuardrailLayer,
    ReassessmentRecord,
    RecertificationTriggerStatus,
    RecertificationTriggerType,
    TrustATEConfiguration,
    TrustBlockedActionRecord,
    TrustCertificationEvidenceRef,
    TrustCircuitBreakerConfig,
    TrustGuardrailPipelineConfig,
    TrustOJEPipelineConfig,
    TrustProofLink,
    TrustRecertificationRequest,
    TrustRecertificationTrigger,
    TrustSafetyPreScreenerRuleSet,
    TrustSignal,
    TrustTierName,
)
from platform.trust.repository import TrustRepository
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from tests.trust_support import build_certification, stamp


class _ScalarSequence:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def all(self) -> list[Any]:
        return list(self._items)


class _ResultStub:
    def __init__(self, *, scalar: Any | None = None, items: list[Any] | None = None) -> None:
        self._scalar = scalar
        self._items = items or []

    def scalar_one_or_none(self) -> Any | None:
        return self._scalar

    def scalars(self) -> _ScalarSequence:
        return _ScalarSequence(self._items)

    def all(self) -> list[Any]:
        return list(self._items)


class _SessionStub:
    def __init__(
        self,
        *,
        execute_results: list[_ResultStub] | None = None,
        scalar_results: list[Any] | None = None,
        get_results: list[Any] | None = None,
    ) -> None:
        self.execute_results = list(execute_results or [])
        self.scalar_results = list(scalar_results or [])
        self.get_results = list(get_results or [])
        self.added: list[Any] = []
        self.flush_count = 0

    def add(self, item: Any) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flush_count += 1

    async def execute(self, statement: Any) -> _ResultStub:
        del statement
        return self.execute_results.pop(0)

    async def scalar(self, statement: Any) -> Any:
        del statement
        return self.scalar_results.pop(0)

    async def get(self, model: Any, ident: Any) -> Any:
        del model, ident
        return self.get_results.pop(0)


@pytest.mark.asyncio
async def test_repository_create_helpers_add_and_flush() -> None:
    session = _SessionStub()
    repo = TrustRepository(session)  # type: ignore[arg-type]
    certification = build_certification()

    await repo.create_certification(certification)
    await repo.create_evidence_ref(
        TrustCertificationEvidenceRef(
            certification_id=certification.id,
            evidence_type=EvidenceType.test_results,
            source_ref_type="suite",
            source_ref_id="suite-1",
        )
    )
    await repo.create_signal(
        TrustSignal(
            agent_id="agent-1",
            signal_type="behavioral_conformance",
            score_contribution=Decimal("1.0000"),
            source_type="test",
            source_id="source-1",
            workspace_id="workspace-1",
        )
    )
    await repo.create_proof_link(
        TrustProofLink(
            signal_id=uuid4(),
            proof_type="proof",
            proof_reference_type="ref",
            proof_reference_id="ref-1",
        )
    )
    await repo.create_trigger(
        TrustRecertificationTrigger(
            agent_id="agent-1",
            agent_revision_id="rev-1",
            trigger_type=RecertificationTriggerType.revision_changed,
            status=RecertificationTriggerStatus.pending,
        )
    )
    await repo.create_blocked_action_record(
        TrustBlockedActionRecord(
            agent_id="agent-1",
            agent_fqn="fleet:agent-1",
            layer=GuardrailLayer.prompt_injection,
            policy_basis="blocked",
            input_context_hash="hash",
        )
    )
    await repo.create_ate_config(
        TrustATEConfiguration(
            workspace_id="workspace-1",
            name="smoke",
            version=1,
            is_active=True,
            test_scenarios=[{"summary": "ok"}],
            scoring_config={},
            timeout_seconds=60,
        )
    )
    await repo.create_guardrail_config(
        TrustGuardrailPipelineConfig(
            workspace_id="workspace-1",
            fleet_id=None,
            config={},
            is_active=True,
        )
    )
    await repo.create_oje_config(
        TrustOJEPipelineConfig(
            workspace_id="workspace-1",
            fleet_id=None,
            observer_fqns=["observer"],
            judge_fqns=["judge"],
            enforcer_fqns=["enforcer"],
            policy_refs=["policy"],
            is_active=True,
        )
    )
    await repo.create_circuit_breaker_config(
        TrustCircuitBreakerConfig(
            workspace_id="workspace-1",
            agent_id="agent-1",
            fleet_id=None,
            failure_threshold=5,
            time_window_seconds=600,
            tripped_ttl_seconds=3600,
            enabled=True,
        )
    )
    await repo.create_rule_set(
        TrustSafetyPreScreenerRuleSet(
            version=1,
            name="rules",
            is_active=True,
            rules_ref="rules.json",
            rule_count=1,
        )
    )

    assert len(session.added) == 11
    assert session.flush_count == 11


@pytest.mark.asyncio
async def test_repository_certifier_contract_and_attachment_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    certifier = stamp(
        Certifier(
            name="Acme Certifier",
            organization="Acme",
            credentials={"credential_id": "cred-1"},
            permitted_scopes=["safety", "quality"],
            is_active=True,
            created_by="admin",
            updated_by="admin",
        )
    )
    contract = stamp(
        AgentContract(
            workspace_id=workspace_id,
            agent_id="agent-1",
            task_scope="Validate responses",
            expected_outputs={"type": "json"},
            quality_thresholds={"accuracy_min": 0.9},
            time_constraint_seconds=30,
            cost_limit_tokens=2000,
            escalation_conditions={"timeout": "warn"},
            success_criteria={"pass_rate": 0.95},
            enforcement_policy="warn",
            is_archived=False,
            created_by="owner",
            updated_by="owner",
        )
    )
    session = _SessionStub(
        execute_results=[
            _ResultStub(scalar=certifier),
            _ResultStub(items=[certifier]),
            _ResultStub(items=[certifier]),
            _ResultStub(scalar=contract),
            _ResultStub(items=[contract]),
            _ResultStub(items=[contract]),
            _ResultStub(scalar={"snapshot": "interaction"}),
            _ResultStub(scalar={"snapshot": "execution"}),
        ],
        scalar_results=[2, 0],
        get_results=[
            None,
            SimpleNamespace(contract_id=uuid4(), contract_snapshot=None),
            SimpleNamespace(contract_id=None, contract_snapshot=None),
            None,
            SimpleNamespace(contract_id=uuid4(), contract_snapshot=None),
            SimpleNamespace(contract_id=None, contract_snapshot=None),
        ],
    )
    repo = TrustRepository(session)  # type: ignore[arg-type]

    created_certifier = await repo.create_certifier(
        Certifier(
            name="Fresh Certifier",
            organization=None,
            credentials=None,
            permitted_scopes=None,
            is_active=True,
            created_by="admin",
            updated_by="admin",
        )
    )
    assert created_certifier in session.added
    assert await repo.get_certifier(certifier.id) == certifier
    assert await repo.list_certifiers() == [certifier]
    assert await repo.list_certifiers(include_inactive=True) == [certifier]

    async def _get_certifier(certifier_id: Any) -> Any:
        del certifier_id
        return certifier

    monkeypatch.setattr(repo, "get_certifier", _get_certifier)
    deactivated = await repo.deactivate_certifier(certifier.id)
    assert deactivated is certifier
    assert certifier.is_active is False

    async def _missing_certifier(certifier_id: Any) -> Any:
        del certifier_id
        return None

    monkeypatch.setattr(repo, "get_certifier", _missing_certifier)
    assert await repo.deactivate_certifier(uuid4()) is None

    created_contract = await repo.create_contract(
        AgentContract(
            workspace_id=workspace_id,
            agent_id="agent-2",
            task_scope="Score prompts",
            expected_outputs=None,
            quality_thresholds=None,
            time_constraint_seconds=None,
            cost_limit_tokens=None,
            escalation_conditions=None,
            success_criteria=None,
            enforcement_policy="throttle",
            is_archived=False,
            created_by="owner",
            updated_by="owner",
        )
    )
    assert created_contract in session.added
    assert await repo.get_contract(contract.id) == contract
    assert await repo.list_contracts(workspace_id, agent_id="agent-1") == [contract]
    assert await repo.list_contracts(workspace_id, include_archived=True) == [contract]

    async def _get_contract(contract_id: Any) -> Any:
        del contract_id
        return contract

    monkeypatch.setattr(repo, "get_contract", _get_contract)
    updated = await repo.update_contract(
        contract.id,
        {"task_scope": "Updated", "cost_limit_tokens": 42},
    )
    assert updated is contract
    assert contract.task_scope == "Updated"
    assert contract.cost_limit_tokens == 42
    archived = await repo.archive_contract(contract.id)
    assert archived is contract
    assert contract.is_archived is True

    async def _missing_contract(contract_id: Any) -> Any:
        del contract_id
        return None

    monkeypatch.setattr(repo, "get_contract", _missing_contract)
    assert await repo.update_contract(uuid4(), {"task_scope": "ignored"}) is None
    assert await repo.archive_contract(uuid4()) is None

    assert await repo.has_inflight_execution_for_contract(contract.id) is True
    assert await repo.has_inflight_execution_for_contract(contract.id) is False
    assert await repo.get_interaction_contract_snapshot(uuid4()) == {"snapshot": "interaction"}
    assert await repo.get_execution_contract_snapshot(uuid4()) == {"snapshot": "execution"}

    interaction_id = uuid4()
    execution_id = uuid4()
    assert await repo.attach_contract_to_interaction(interaction_id, contract.id, {"v": 1}) is None
    with pytest.raises(ContractConflictError):
        await repo.attach_contract_to_interaction(interaction_id, contract.id, {"v": 1})
    attached_interaction = await repo.attach_contract_to_interaction(
        interaction_id,
        contract.id,
        {"v": 2},
    )
    assert attached_interaction.contract_id == contract.id
    assert attached_interaction.contract_snapshot == {"v": 2}

    assert await repo.attach_contract_to_execution(execution_id, contract.id, {"v": 3}) is None
    with pytest.raises(ContractConflictError):
        await repo.attach_contract_to_execution(execution_id, contract.id, {"v": 3})
    attached_execution = await repo.attach_contract_to_execution(
        execution_id,
        contract.id,
        {"v": 4},
    )
    assert attached_execution.contract_id == contract.id
    assert attached_execution.contract_snapshot == {"v": 4}


@pytest.mark.asyncio
async def test_repository_reassessment_recertification_and_compliance_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    certification = build_certification(status=CertificationStatus.active)
    reassessment = stamp(
        ReassessmentRecord(
            certification_id=certification.id,
            verdict="pass",
            reassessor_id="reviewer",
            notes="ok",
            created_by="reviewer",
            updated_by="reviewer",
        )
    )
    request = stamp(
        TrustRecertificationRequest(
            certification_id=certification.id,
            trigger_type="signal",
            trigger_reference="run-1",
            deadline=datetime.now(UTC) + timedelta(days=1),
            resolution_status="pending",
            dismissal_justification=None,
        )
    )
    breach = stamp(
        ContractBreachEvent(
            contract_id=uuid4(),
            target_type="execution",
            target_id=uuid4(),
            breached_term="quality_threshold",
            observed_value={"accuracy_min": 0.5},
            threshold_value={"accuracy_min": 0.9},
            enforcement_action="warn",
            enforcement_outcome="success",
            contract_snapshot={"contract": "snapshot"},
        )
    )
    start = datetime.now(UTC) - timedelta(days=1)
    end = datetime.now(UTC) + timedelta(days=1)
    execution_row = SimpleNamespace(
        id=uuid4(),
        created_at=(datetime.now(UTC) - timedelta(hours=1)).replace(
            minute=15, second=0, microsecond=0
        ),
        contract_id=breach.contract_id,
    )
    interaction_row = SimpleNamespace(
        id=uuid4(),
        created_at=datetime.now(UTC).replace(minute=45, second=0, microsecond=0),
        contract_id=breach.contract_id,
    )
    breach.target_id = execution_row.id
    session = _SessionStub(
        execute_results=[
            _ResultStub(items=[breach]),
            _ResultStub(items=[reassessment]),
            _ResultStub(scalar=request),
            _ResultStub(items=[request]),
            _ResultStub(items=[request]),
            _ResultStub(items=[certification]),
            _ResultStub(items=[execution_row]),
            _ResultStub(items=[interaction_row]),
            _ResultStub(items=[breach]),
            _ResultStub(items=[execution_row]),
            _ResultStub(items=[]),
            _ResultStub(items=[execution_row]),
            _ResultStub(items=[interaction_row]),
            _ResultStub(items=[breach]),
        ],
        scalar_results=[3],
    )
    repo = TrustRepository(session)  # type: ignore[arg-type]

    created_breach = await repo.create_breach_event(
        ContractBreachEvent(
            contract_id=uuid4(),
            target_type="interaction",
            target_id=uuid4(),
            breached_term="timeout",
            observed_value={"seconds": 31},
            threshold_value={"seconds": 30},
            enforcement_action="throttle",
            enforcement_outcome="applied",
            contract_snapshot={},
        )
    )
    assert created_breach in session.added

    listed_breaches, total_breaches = await repo.list_breach_events(
        breach.contract_id,
        target_type="execution",
        start=start,
        end=end,
    )
    assert listed_breaches == [breach]
    assert total_breaches == 3

    created_reassessment = await repo.create_reassessment(certification.id, reassessment)
    assert created_reassessment is reassessment
    assert reassessment.certification_id == certification.id
    assert await repo.list_reassessments(certification.id) == [reassessment]

    created_request = await repo.create_recertification_request(request)
    assert created_request is request
    assert await repo.get_recertification_request(request.id) == request
    assert await repo.list_recertification_requests(
        certification_id=certification.id,
        status="pending",
    ) == [request]
    assert await repo.get_pending_requests_past_deadline(datetime.now(UTC)) == [request]

    async def _get_request(request_id: Any) -> Any:
        del request_id
        return request

    monkeypatch.setattr(repo, "get_recertification_request", _get_request)
    resolved = await repo.resolve_recertification_request(
        request.id,
        "dismissed",
        "manually reviewed",
    )
    assert resolved is request
    assert request.resolution_status == "dismissed"
    assert request.dismissal_justification == "manually reviewed"

    async def _missing_request(request_id: Any) -> Any:
        del request_id
        return None

    monkeypatch.setattr(repo, "get_recertification_request", _missing_request)
    assert await repo.resolve_recertification_request(uuid4(), "dismissed") is None

    assert await repo.get_active_or_expiring_certifications_for_agent("agent-1") == [certification]

    workspace_stats = await repo.get_compliance_stats(
        "workspace",
        str(uuid4()),
        start,
        end,
        "hourly",
    )
    assert workspace_stats["total_contract_attached"] == 2
    assert workspace_stats["compliant"] == 1
    assert workspace_stats["warned"] == 1
    assert workspace_stats["breach_by_term"] == {"quality_threshold": 1}
    assert len(workspace_stats["trend"]) == 2

    fleet_stats = await repo.get_compliance_stats(
        "fleet",
        str(uuid4()),
        start,
        end,
        "daily",
    )
    agent_stats = await repo.get_compliance_stats(
        "agent",
        "agent-1",
        start,
        end,
        "daily",
    )
    assert fleet_stats["total_contract_attached"] == 1
    assert fleet_stats["trend"][0]["total"] == 1
    assert agent_stats["warned"] == 1


@pytest.mark.asyncio
async def test_repository_certification_queries_and_counts() -> None:
    certification = build_certification(status=CertificationStatus.active)
    session = _SessionStub(
        execute_results=[
            _ResultStub(scalar=certification),
            _ResultStub(items=[certification]),
            _ResultStub(items=[certification]),
            _ResultStub(items=[certification]),
            _ResultStub(scalar=certification),
            _ResultStub(items=[certification]),
        ],
        scalar_results=[2, 1],
    )
    repo = TrustRepository(session)  # type: ignore[arg-type]

    assert await repo.get_certification(certification.id) == certification
    assert await repo.list_certifications_for_agent("agent-1") == [certification]
    assert await repo.list_active_certifications_for_agent("agent-1") == [certification]
    assert await repo.list_stale_certifications(datetime.now(UTC)) == [certification]
    assert await repo.get_latest_certification_for_agent("agent-1") == certification
    assert await repo.list_expiry_approaching_certifications(
        now=datetime.now(UTC),
        within_days=7,
    ) == [certification]
    assert await repo.count_guardrail_evaluations("agent-1", since=datetime.now(UTC)) == 2
    assert await repo.count_blocked_actions("agent-1", since=datetime.now(UTC)) == 1


@pytest.mark.asyncio
async def test_repository_tier_and_signal_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    signal = stamp(
        TrustSignal(
            agent_id="agent-1",
            signal_type="behavioral_conformance",
            score_contribution=Decimal("0.7"),
            source_type="test",
            source_id="source-1",
            workspace_id="workspace-1",
        )
    )
    session = _SessionStub(
        execute_results=[
            _ResultStub(scalar=None),
            _ResultStub(items=[signal]),
        ],
        scalar_results=[1],
    )
    repo = TrustRepository(session)  # type: ignore[arg-type]

    tier = await repo.upsert_trust_tier(
        agent_id="agent-1",
        agent_fqn="fleet:agent-1",
        tier=TrustTierName.certified,
        trust_score=Decimal("0.9"),
        certification_component=Decimal("1.0"),
        guardrail_component=Decimal("1.0"),
        behavioral_component=Decimal("0.7"),
        last_computed_at=datetime.now(UTC),
    )
    assert tier.tier == TrustTierName.certified

    async def _get_tier(agent_id: str) -> Any:
        del agent_id
        return tier

    monkeypatch.setattr(repo, "get_tier", _get_tier)
    updated = await repo.upsert_trust_tier(
        agent_id="agent-1",
        agent_fqn="fleet:agent-1",
        tier=TrustTierName.provisional,
        trust_score=Decimal("0.5"),
        certification_component=Decimal("0.5"),
        guardrail_component=Decimal("0.5"),
        behavioral_component=Decimal("0.5"),
        last_computed_at=datetime.now(UTC),
    )
    listed, total = await repo.list_trust_signals_for_agent(
        "agent-1",
        since=datetime.now(UTC) - timedelta(days=1),
        signal_type="behavioral_conformance",
    )

    assert updated.tier == TrustTierName.provisional
    assert total == 1
    assert listed == [signal]


@pytest.mark.asyncio
async def test_repository_trigger_and_blocked_action_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trigger = stamp(
        TrustRecertificationTrigger(
            agent_id="agent-1",
            agent_revision_id="rev-1",
            trigger_type=RecertificationTriggerType.revision_changed,
            status=RecertificationTriggerStatus.pending,
        )
    )
    blocked = stamp(
        TrustBlockedActionRecord(
            agent_id="agent-1",
            agent_fqn="fleet:agent-1",
            layer=GuardrailLayer.prompt_injection,
            policy_basis="blocked",
            input_context_hash="hash",
        )
    )
    session = _SessionStub(
        execute_results=[
            _ResultStub(scalar=trigger),
            _ResultStub(scalar=trigger),
            _ResultStub(items=[trigger]),
            _ResultStub(scalar=blocked),
            _ResultStub(items=[blocked]),
        ],
        scalar_results=[1],
    )
    repo = TrustRepository(session)  # type: ignore[arg-type]

    assert await repo.get_trigger(trigger.id) == trigger
    assert (
        await repo.get_pending_trigger(
            agent_id="agent-1",
            agent_revision_id="rev-1",
            trigger_type=RecertificationTriggerType.revision_changed,
        )
        == trigger
    )
    assert await repo.list_triggers(agent_id="agent-1") == [trigger]
    async def _list_triggers(**kwargs: Any) -> list[Any]:
        del kwargs
        return [trigger]

    monkeypatch.setattr(repo, "list_triggers", _list_triggers)
    assert await repo.list_pending_triggers() == [trigger]
    assert await repo.get_blocked_action(blocked.id) == blocked
    listed, total = await repo.list_blocked_actions_paginated(agent_id="agent-1")
    assert listed == [blocked]
    assert total == 1


@pytest.mark.asyncio
async def test_repository_config_resolution_and_upserts(monkeypatch: pytest.MonkeyPatch) -> None:
    fallback_guardrail = stamp(
        TrustGuardrailPipelineConfig(
            workspace_id="workspace-1",
            fleet_id=None,
            config={"action_commit": {"enabled": True}},
            is_active=True,
        )
    )
    oje_config = stamp(
        TrustOJEPipelineConfig(
            workspace_id="workspace-1",
            fleet_id=None,
            observer_fqns=["observer"],
            judge_fqns=["judge"],
            enforcer_fqns=["enforcer"],
            policy_refs=["policy"],
            is_active=True,
        )
    )
    cb_config = stamp(
        TrustCircuitBreakerConfig(
            workspace_id="workspace-1",
            agent_id=None,
            fleet_id=None,
            failure_threshold=5,
            time_window_seconds=600,
            tripped_ttl_seconds=3600,
            enabled=True,
        )
    )
    session = _SessionStub(
        execute_results=[
            _ResultStub(scalar=None),
            _ResultStub(scalar=fallback_guardrail),
            _ResultStub(scalar=oje_config),
            _ResultStub(scalar=oje_config),
            _ResultStub(items=[oje_config]),
            _ResultStub(scalar=oje_config),
            _ResultStub(scalar=cb_config),
            _ResultStub(scalar=cb_config),
            _ResultStub(items=[cb_config]),
        ]
    )
    repo = TrustRepository(session)  # type: ignore[arg-type]

    assert await repo.get_guardrail_config("workspace-1", "fleet-a") == fallback_guardrail
    async def _get_guardrail_config(
        workspace_id: str,
        fleet_id: str | None,
    ) -> Any:
        del workspace_id, fleet_id
        return fallback_guardrail

    monkeypatch.setattr(repo, "get_guardrail_config", _get_guardrail_config)
    updated_guardrail = await repo.upsert_guardrail_config(
        workspace_id="workspace-1",
        fleet_id=None,
        config={"action_commit": {"enabled": False}},
        is_active=False,
    )
    assert updated_guardrail.config["action_commit"]["enabled"] is False
    assert await repo.get_oje_config("workspace-1", None) == oje_config
    assert await repo.get_oje_config_by_id(oje_config.id) == oje_config
    assert await repo.list_oje_configs("workspace-1") == [oje_config]
    deactivated = await repo.deactivate_oje_config(oje_config.id)
    assert deactivated is oje_config
    assert await repo.get_circuit_breaker_config(workspace_id="workspace-1") == cb_config
    upserted = await repo.upsert_circuit_breaker_config(
        workspace_id="workspace-1",
        agent_id=None,
        fleet_id=None,
        failure_threshold=9,
        time_window_seconds=120,
        tripped_ttl_seconds=240,
        enabled=False,
    )
    listed = await repo.list_circuit_breaker_configs("workspace-1")
    assert upserted.failure_threshold == 9
    assert listed == [cb_config]


@pytest.mark.asyncio
async def test_repository_ate_and_prescreener_helpers() -> None:
    ate_config = stamp(
        TrustATEConfiguration(
            workspace_id="workspace-1",
            name="smoke",
            version=1,
            is_active=True,
            test_scenarios=[{"summary": "ok"}],
            scoring_config={},
            timeout_seconds=120,
        )
    )
    rule_set = stamp(
        TrustSafetyPreScreenerRuleSet(
            version=1,
            name="rules",
            is_active=True,
            rules_ref="rules.json",
            rule_count=2,
        )
    )
    session = _SessionStub(
        execute_results=[
            _ResultStub(scalar=ate_config),
            _ResultStub(items=[ate_config]),
            _ResultStub(items=[ate_config]),
            _ResultStub(items=[ate_config]),
            _ResultStub(scalar=rule_set),
            _ResultStub(scalar=rule_set),
            _ResultStub(scalar=rule_set),
            _ResultStub(items=[rule_set]),
            _ResultStub(items=[rule_set]),
        ],
        scalar_results=[1, 2],
    )
    repo = TrustRepository(session)  # type: ignore[arg-type]

    assert await repo.get_ate_config(ate_config.id) == ate_config
    assert await repo.list_ate_configs_for_workspace("workspace-1") == [ate_config]
    assert await repo.list_ate_config_versions("workspace-1", "smoke") == [ate_config]
    assert await repo.get_latest_ate_config_version("workspace-1", "smoke") == 1
    await repo.deactivate_ate_configs("workspace-1", "smoke")
    assert ate_config.is_active is False
    assert await repo.get_rule_set(rule_set.id) == rule_set
    assert await repo.get_rule_set_by_version(1) == rule_set
    assert await repo.get_active_prescreener_rule_set() == rule_set
    assert await repo.list_rule_sets() == [rule_set]
    assert await repo.next_rule_set_version() == 3
    activated = await repo.set_active_rule_set(rule_set.id)
    assert activated is rule_set


@pytest.mark.asyncio
async def test_repository_guardrail_oje_and_missing_rule_set_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guardrail_fleet = stamp(
        TrustGuardrailPipelineConfig(
            workspace_id="workspace-1",
            fleet_id="fleet-1",
            config={"action_commit": {"enabled": True}},
            is_active=True,
        )
    )
    guardrail_default = stamp(
        TrustGuardrailPipelineConfig(
            workspace_id="workspace-1",
            fleet_id=None,
            config={"action_commit": {"enabled": False}},
            is_active=True,
        )
    )
    oje_fleet = stamp(
        TrustOJEPipelineConfig(
            workspace_id="workspace-1",
            fleet_id="fleet-1",
            observer_fqns=["observer"],
            judge_fqns=["judge"],
            enforcer_fqns=["enforcer"],
            policy_refs=["policy"],
            is_active=True,
        )
    )
    rule_set = stamp(
        TrustSafetyPreScreenerRuleSet(
            version=3,
            name="rules-3",
            is_active=False,
            rules_ref="rules-3.json",
            rule_count=1,
        )
    )
    session = _SessionStub(
        execute_results=[
            _ResultStub(items=[guardrail_default]),
            _ResultStub(scalar=guardrail_fleet),
            _ResultStub(scalar=oje_fleet),
            _ResultStub(scalar=None),
            _ResultStub(scalar=None),
            _ResultStub(scalar=None),
            _ResultStub(items=[rule_set]),
        ]
    )
    repo = TrustRepository(session)  # type: ignore[arg-type]

    listed_guardrails = await repo.list_guardrail_configs("workspace-1")
    assert listed_guardrails == [guardrail_default]
    assert await repo.get_guardrail_config("workspace-1", "fleet-1") == guardrail_fleet
    assert await repo.get_oje_config("workspace-1", "fleet-1") == oje_fleet
    assert await repo.get_oje_config("workspace-404", "fleet-404") is None

    async def _missing_guardrail(
        workspace_id: str,
        fleet_id: str | None,
    ) -> Any:
        del workspace_id, fleet_id
        return None

    monkeypatch.setattr(repo, "get_guardrail_config", _missing_guardrail)
    created = await repo.upsert_guardrail_config(
        workspace_id="workspace-2",
        fleet_id="fleet-2",
        config={"action_commit": {"enabled": True}},
        is_active=True,
    )
    assert created in session.added
    assert await repo.deactivate_oje_config(uuid4()) is None

    with pytest.raises(LookupError):
        await repo.set_active_rule_set(uuid4())


@pytest.mark.asyncio
async def test_repository_circuit_breaker_filter_and_create_branches() -> None:
    trigger = stamp(
        TrustRecertificationTrigger(
            agent_id="agent-1",
            agent_revision_id="rev-1",
            trigger_type=RecertificationTriggerType.revision_changed,
            status=RecertificationTriggerStatus.pending,
        )
    )
    blocked = stamp(
        TrustBlockedActionRecord(
            agent_id="agent-1",
            agent_fqn="fleet:agent-1",
            layer=GuardrailLayer.memory_write,
            policy_basis="blocked",
            input_context_hash="hash",
            workspace_id="workspace-1",
        ),
        created_at=datetime.now(UTC),
    )
    cb_agent = stamp(
        TrustCircuitBreakerConfig(
            workspace_id="workspace-1",
            agent_id="agent-1",
            fleet_id=None,
            failure_threshold=5,
            time_window_seconds=600,
            tripped_ttl_seconds=3600,
            enabled=True,
        )
    )
    cb_fleet = stamp(
        TrustCircuitBreakerConfig(
            workspace_id="workspace-1",
            agent_id=None,
            fleet_id="fleet-1",
            failure_threshold=6,
            time_window_seconds=600,
            tripped_ttl_seconds=3600,
            enabled=True,
        )
    )
    cb_by_id = stamp(
        TrustCircuitBreakerConfig(
            workspace_id="workspace-2",
            agent_id=None,
            fleet_id=None,
            failure_threshold=7,
            time_window_seconds=600,
            tripped_ttl_seconds=3600,
            enabled=True,
        )
    )
    session = _SessionStub(
        execute_results=[
            _ResultStub(items=[trigger]),
            _ResultStub(items=[blocked]),
            _ResultStub(scalar=cb_agent),
            _ResultStub(scalar=cb_fleet),
            _ResultStub(scalar=None),
            _ResultStub(scalar=None),
            _ResultStub(scalar=None),
            _ResultStub(scalar=cb_by_id),
            _ResultStub(scalar=None),
        ],
        scalar_results=[1],
    )
    repo = TrustRepository(session)  # type: ignore[arg-type]

    assert await repo.list_triggers(status=RecertificationTriggerStatus.pending) == [trigger]
    listed, total = await repo.list_blocked_actions_paginated(
        layer=GuardrailLayer.memory_write,
        workspace_id="workspace-1",
        since=blocked.created_at - timedelta(seconds=1),
        until=blocked.created_at + timedelta(seconds=1),
    )
    assert listed == [blocked]
    assert total == 1
    assert (
        await repo.get_circuit_breaker_config(workspace_id="workspace-1", agent_id="agent-1")
        == cb_agent
    )
    assert (
        await repo.get_circuit_breaker_config(workspace_id="workspace-1", fleet_id="fleet-1")
        == cb_fleet
    )
    assert (
        await repo.get_circuit_breaker_config(
            workspace_id="workspace-404",
            agent_id="missing-agent",
            fleet_id="missing-fleet",
        )
        is None
    )
    assert await repo.get_circuit_breaker_config_by_id(cb_by_id.id) == cb_by_id

    created = await repo.upsert_circuit_breaker_config(
        workspace_id="workspace-3",
        agent_id=None,
        fleet_id="fleet-9",
        failure_threshold=9,
        time_window_seconds=90,
        tripped_ttl_seconds=180,
        enabled=False,
    )
    assert created in session.added
