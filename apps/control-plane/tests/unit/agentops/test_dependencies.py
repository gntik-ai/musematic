from __future__ import annotations

from platform.agentops import dependencies as deps
from platform.agentops.dependencies import (
    AgentOpsEvalAdapter,
    AgentOpsPolicyAdapter,
    AgentOpsRegistryAdapter,
    AgentOpsTrustAdapter,
    AgentOpsWorkflowAdapter,
    _ate_pre_check,
    _get_clickhouse,
    _get_producer,
    _get_reasoning_client,
    _get_redis,
    _get_settings,
    build_agentops_service,
    get_agentops_service,
    get_agentops_workspace_id,
    resolve_workspace_id,
)
from platform.common.exceptions import ValidationError
from platform.registry.models import AgentProfile, AgentRevision, LifecycleStatus
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest


class _SessionExecuteResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


@pytest.mark.asyncio
async def test_trust_adapter_methods_delegate_to_underlying_services() -> None:
    certification_service = SimpleNamespace(
        is_agent_certified=AsyncMock(return_value=True),
        expire_stale=AsyncMock(return_value=3),
        repository=SimpleNamespace(
            get_latest_certification_for_agent=AsyncMock(
                return_value=SimpleNamespace(status="active")
            )
        ),
    )
    trust_tier_service = SimpleNamespace(get_tier=AsyncMock(return_value=SimpleNamespace(tier=2)))
    recertification_service = SimpleNamespace(
        create_trigger=AsyncMock(),
        repository=SimpleNamespace(
            list_triggers=AsyncMock(return_value=[SimpleNamespace(id=uuid4())]),
            list_expiry_approaching_certifications=AsyncMock(
                return_value=[
                    SimpleNamespace(
                        agent_id="finance:agent",
                        id=uuid4(),
                        status="active",
                        expires_at=None,
                    )
                ]
            ),
        ),
    )
    adapter = AgentOpsTrustAdapter(
        certification_service=certification_service,
        trust_tier_service=trust_tier_service,
        recertification_service=recertification_service,
    )

    assert await adapter.is_agent_certified("finance:agent", uuid4()) is True
    assert (await adapter.get_agent_trust_tier("finance:agent", uuid4())).tier == 2
    assert await adapter.expire_stale_certifications() == 3
    assert (await adapter.get_latest_certification("finance:agent")).status == "active"
    assert len(await adapter.list_pending_triggers("finance:agent")) == 1
    assert len(await adapter.list_upcoming_expirations("finance:agent", 7)) == 1


@pytest.mark.asyncio
async def test_eval_adapter_resolves_default_ate_config_and_starts_run() -> None:
    workspace_id = uuid4()
    config_id = uuid4()
    repository = SimpleNamespace(
        list_ate_configs=AsyncMock(return_value=([SimpleNamespace(id=config_id)], 1)),
        get_ate_config=AsyncMock(
            return_value=SimpleNamespace(
                id=config_id,
                scenarios=[
                    {
                        "id": "1",
                        "name": "demo",
                        "input_data": {},
                        "expected_output": "ok",
                    }
                ],
            )
        ),
        create_ate_run=AsyncMock(side_effect=lambda run: run),
    )
    adapter = AgentOpsEvalAdapter(
        eval_suite_service=SimpleNamespace(get_run_summary=AsyncMock(return_value={"id": "run"})),
        evaluation_repository=repository,  # type: ignore[arg-type]
    )

    assert await adapter.resolve_default_ate_config(workspace_id) == config_id
    run = await adapter.start_ate_run(
        ate_config_id=config_id,
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        candidate_revision_id=uuid4(),
    )
    assert run.ate_config_id == config_id


@pytest.mark.asyncio
async def test_eval_adapter_handles_missing_config_and_default_noop_methods() -> None:
    workspace_id = uuid4()
    repository = SimpleNamespace(
        list_ate_configs=AsyncMock(return_value=([], 0)),
        get_ate_config=AsyncMock(return_value=None),
        create_ate_run=AsyncMock(),
    )
    eval_suite_service = SimpleNamespace(get_run_summary=AsyncMock(return_value={"id": "run-1"}))
    adapter = AgentOpsEvalAdapter(
        eval_suite_service=eval_suite_service,
        evaluation_repository=repository,  # type: ignore[arg-type]
    )

    assert await adapter.get_latest_agent_score("finance:agent", workspace_id) is None
    assert await adapter.get_run_results(uuid4()) == {"id": "run-1"}
    assert await adapter.submit_to_ate(uuid4(), uuid4(), workspace_id) is None
    assert await adapter.get_human_grade_aggregate("finance:agent", workspace_id, 7) is None
    assert await adapter.resolve_default_ate_config(workspace_id) is None
    assert (
        await adapter.start_ate_run(
            ate_config_id=uuid4(),
            workspace_id=workspace_id,
            agent_fqn="finance:agent",
            candidate_revision_id=uuid4(),
        )
        is None
    )


@pytest.mark.asyncio
async def test_registry_adapter_can_list_active_agents_and_create_candidate_revision(
    monkeypatch,
) -> None:
    workspace_id = uuid4()
    profile_id = uuid4()
    revision_id = uuid4()
    candidate_id = uuid4()
    profile = AgentProfile(
        id=profile_id,
        workspace_id=workspace_id,
        namespace_id=None,
        local_name="agent",
        fqn="finance:agent",
        display_name="Finance Agent",
        purpose="Purpose",
        approach="Approach",
        role_types=["assistant"],
        custom_role_description=None,
        visibility_agents=[],
        visibility_tools=[],
        tags=[],
        status=LifecycleStatus.published,
        maturity_level=1,
        embedding_status="pending",
        needs_reindex=False,
        created_by=uuid4(),
    )
    revision = AgentRevision(
        id=revision_id,
        workspace_id=workspace_id,
        agent_profile_id=profile_id,
        version="1.0.0",
        sha256_digest="a" * 64,
        storage_key="agents/finance/package.tar.gz",
        manifest_snapshot={"version": "1.0.0"},
        uploaded_by=uuid4(),
    )
    session = SimpleNamespace(execute=AsyncMock(return_value=_SessionExecuteResult([profile])))
    adapter = AgentOpsRegistryAdapter(session=session)  # type: ignore[arg-type]
    monkeypatch.setattr(
        adapter.repository,
        "get_latest_revision",
        AsyncMock(return_value=revision),
    )
    monkeypatch.setattr(
        adapter,
        "get_agent_revision",
        AsyncMock(return_value=revision),
    )
    monkeypatch.setattr(
        adapter.repository,
        "insert_revision",
        AsyncMock(side_effect=lambda **kwargs: SimpleNamespace(id=candidate_id, **kwargs)),
    )

    active_agents = await adapter.list_active_agents(workspace_id)
    candidate = await adapter.create_candidate_revision(
        agent_fqn="finance:agent",
        base_revision_id=revision_id,
        workspace_id=workspace_id,
        adjustments=[{"rule_type": "quality_trend", "action": "refresh_context_profile"}],
        actor_id=uuid4(),
    )

    assert active_agents[0]["agent_fqn"] == "finance:agent"
    assert candidate.id == candidate_id


@pytest.mark.asyncio
async def test_registry_adapter_fallback_and_passthrough_paths() -> None:
    workspace_id = uuid4()
    profile_id = uuid4()
    revision_id = uuid4()
    session = SimpleNamespace(execute=AsyncMock(return_value=_SessionExecuteResult([])))
    passthrough_service = SimpleNamespace(
        get_agent_revision=AsyncMock(return_value=SimpleNamespace(id=revision_id)),
        set_marketplace_visibility=AsyncMock(),
        list_active_agents=AsyncMock(return_value=[{"agent_fqn": "finance:agent"}]),
    )
    adapter = AgentOpsRegistryAdapter(
        session=session,  # type: ignore[arg-type]
        registry_service=passthrough_service,
    )

    assert await adapter.get_agent_revision("finance:agent", revision_id) is not None
    await adapter.set_marketplace_visibility("finance:agent", False, workspace_id)
    assert await adapter.list_active_agents(workspace_id) == [{"agent_fqn": "finance:agent"}]

    fallback_adapter = AgentOpsRegistryAdapter(session=session)  # type: ignore[arg-type]
    revision = AgentRevision(
        id=revision_id,
        workspace_id=workspace_id,
        agent_profile_id=profile_id,
        version="1.0.0",
        sha256_digest="a" * 64,
        storage_key="agents/pkg.tgz",
        manifest_snapshot={},
        uploaded_by=uuid4(),
    )
    fallback_adapter.repository.get_revision_by_id = AsyncMock(  # type: ignore[method-assign]
        return_value=revision
    )
    fallback_adapter.repository.get_agent_by_id_any = AsyncMock(
        return_value=AgentProfile(
            id=profile_id,
            workspace_id=workspace_id,
            namespace_id=None,
            local_name="agent",
            fqn="finance:agent",
            display_name="Finance Agent",
            purpose="Purpose",
            approach="Approach",
            role_types=["assistant"],
            custom_role_description=None,
            visibility_agents=[],
            visibility_tools=[],
            tags=[],
            status=LifecycleStatus.published,
            maturity_level=1,
            embedding_status="pending",
            needs_reindex=False,
            created_by=uuid4(),
        )
    )
    fallback_adapter.repository.get_latest_revision = AsyncMock(return_value=None)  # type: ignore[method-assign]

    assert await fallback_adapter.get_agent_revision("finance:agent", revision_id) is not None
    assert await fallback_adapter.get_agent_revision("other:agent", uuid4()) is None
    fallback_adapter.get_agent_revision = AsyncMock(return_value=None)  # type: ignore[method-assign]
    assert await fallback_adapter.create_candidate_revision(
        agent_fqn="finance:agent",
        base_revision_id=uuid4(),
        workspace_id=workspace_id,
        adjustments=[],
        actor_id=uuid4(),
    ) is None


def test_resolve_workspace_id_supports_explicit_role_and_errors() -> None:
    request = SimpleNamespace(headers={})
    explicit_workspace_id = uuid4()
    current_user = {"workspace_id": str(explicit_workspace_id)}
    assert resolve_workspace_id(request, current_user) == explicit_workspace_id

    role_workspace = uuid4()
    resolved = resolve_workspace_id(
        request,
        {"roles": [{"workspace_id": str(role_workspace)}]},
    )
    assert resolved == role_workspace

    with pytest.raises(ValidationError):
        resolve_workspace_id(request, {})


def test_ate_pre_check_reports_missing_scenarios_and_fields() -> None:
    empty = SimpleNamespace(scenarios=[])
    partial = SimpleNamespace(scenarios=[{"id": "1", "name": "demo"}])

    assert _ate_pre_check(empty)[0]["code"] == "ATE_SCENARIOS_REQUIRED"
    assert any(item["field"] == "input_data" for item in _ate_pre_check(partial))


@pytest.mark.asyncio
async def test_dependency_helpers_and_adapter_defaults_cover_request_accessors() -> None:
    settings = object()
    kafka = object()
    redis = object()
    clickhouse = object()
    reasoning = object()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={
                    "kafka": kafka,
                    "redis": redis,
                    "clickhouse": clickhouse,
                    "reasoning_engine": reasoning,
                },
            )
        ),
        headers={"X-Workspace-ID": str(uuid4())},
    )

    assert _get_settings(request) is settings
    assert _get_producer(request) is kafka
    assert _get_redis(request) is redis
    assert _get_clickhouse(request) is clickhouse
    assert _get_reasoning_client(request) is reasoning
    assert await get_agentops_workspace_id(request, {"roles": []}) == UUID(
        request.headers["X-Workspace-ID"]
    )

    policy_adapter = AgentOpsPolicyAdapter(policy_service=SimpleNamespace())
    workflow_adapter = AgentOpsWorkflowAdapter(workflow_service=SimpleNamespace())
    assert (
        await policy_adapter.evaluate_conformance("finance:agent", uuid4(), uuid4())
    ) == {"passed": True, "violations": []}
    assert await workflow_adapter.find_workflows_using_agent("finance:agent", uuid4()) == []


@pytest.mark.asyncio
async def test_get_agentops_service_delegates_to_builder(monkeypatch) -> None:
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(),
                clients={
                    "kafka": object(),
                    "redis": object(),
                    "clickhouse": object(),
                    "reasoning_engine": object(),
                },
            )
        )
    )
    session = SimpleNamespace()
    built = SimpleNamespace(name="agentops-service")
    monkeypatch.setattr(deps, "build_agentops_service", lambda **kwargs: built)

    assert await get_agentops_service(request, session) is built


def test_build_agentops_service_wires_expected_adapters(monkeypatch) -> None:
    session = SimpleNamespace()
    settings = SimpleNamespace()
    producer = object()
    redis_client = object()
    clickhouse_client = object()
    reasoning_client = object()

    monkeypatch.setattr(
        deps,
        "AgentOpsRepository",
        lambda session: SimpleNamespace(session=session),
    )
    monkeypatch.setattr(
        deps,
        "AgentOpsEventPublisher",
        lambda producer: SimpleNamespace(producer=producer),
    )
    monkeypatch.setattr(
        deps,
        "GovernanceEventPublisher",
        lambda repository, event_publisher: SimpleNamespace(
            repository=repository,
            event_publisher=event_publisher,
        ),
    )
    monkeypatch.setattr(
        deps,
        "build_certification_service",
        lambda session, settings, producer: SimpleNamespace(),
    )
    monkeypatch.setattr(
        deps,
        "build_trust_tier_service",
        lambda session, settings, producer: SimpleNamespace(),
    )
    monkeypatch.setattr(
        deps,
        "build_recertification_service",
        lambda session, settings, producer: SimpleNamespace(repository=SimpleNamespace()),
    )
    monkeypatch.setattr(
        deps,
        "build_eval_suite_service",
        lambda session, settings, producer: SimpleNamespace(),
    )
    monkeypatch.setattr(deps, "EvaluationRepository", lambda session: SimpleNamespace())
    monkeypatch.setattr(deps, "build_policy_service", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(deps, "build_workflow_service", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(deps, "AgentOpsService", lambda **kwargs: SimpleNamespace(**kwargs))

    service = build_agentops_service(
        session=session,  # type: ignore[arg-type]
        settings=settings,
        producer=producer,
        redis_client=redis_client,  # type: ignore[arg-type]
        clickhouse_client=clickhouse_client,
        reasoning_client=reasoning_client,  # type: ignore[arg-type]
    )

    assert service.redis_client is redis_client
    assert service.clickhouse_client is clickhouse_client
