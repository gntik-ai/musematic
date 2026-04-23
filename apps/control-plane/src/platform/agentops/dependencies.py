from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from platform.agentops.events import AgentOpsEventPublisher, GovernanceEventPublisher
from platform.agentops.repository import AgentOpsRepository
from platform.agentops.service import AgentOpsService
from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.clients.reasoning_engine import ReasoningEngineClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user, get_db
from platform.common.events.producer import EventProducer
from platform.common.exceptions import ValidationError
from platform.evaluation.dependencies import build_eval_suite_service
from platform.evaluation.models import ATERun, ATERunStatus
from platform.evaluation.repository import EvaluationRepository
from platform.policies.dependencies import build_policy_service
from platform.registry.models import AgentProfile, LifecycleStatus
from platform.registry.repository import RegistryRepository
from platform.trust.dependencies import (
    build_certification_service,
    build_recertification_service,
    build_trust_tier_service,
)
from platform.trust.models import RecertificationTriggerStatus, RecertificationTriggerType
from platform.workflows.dependencies import build_workflow_service
from typing import Annotated, Any, cast
from uuid import UUID, uuid4

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class AgentOpsTrustAdapter:
    def __init__(
        self,
        *,
        certification_service: Any,
        trust_tier_service: Any,
        recertification_service: Any,
    ) -> None:
        self.certification_service = certification_service
        self.trust_tier_service = trust_tier_service
        self.recertification_service = recertification_service

    async def is_agent_certified(self, agent_fqn: str, revision_id: UUID) -> bool:
        return bool(
            await self.certification_service.is_agent_certified(
                agent_fqn,
                str(revision_id),
            )
        )

    async def get_agent_trust_tier(self, agent_fqn: str, workspace_id: UUID) -> Any:
        del workspace_id
        return await self.trust_tier_service.get_tier(agent_fqn)

    async def get_guardrail_pass_rate(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        window_days: int,
    ) -> float:
        del agent_fqn, workspace_id, window_days
        return 1.0

    async def trigger_recertification(
        self,
        agent_fqn: str,
        revision_id: UUID,
        trigger_reason: str,
    ) -> None:
        await self.recertification_service.create_trigger(
            agent_fqn,
            str(revision_id),
            RecertificationTriggerType.policy_changed,
            {"event_type": trigger_reason},
        )

    async def expire_stale_certifications(self) -> int:
        return int(await self.certification_service.expire_stale())

    async def get_latest_certification(self, agent_fqn: str) -> Any:
        return await self.certification_service.repository.get_latest_certification_for_agent(
            agent_fqn
        )

    async def list_pending_triggers(self, agent_fqn: str) -> list[Any]:
        return cast(
            list[Any],
            await self.recertification_service.repository.list_triggers(
                agent_id=agent_fqn,
                status=RecertificationTriggerStatus.pending,
            ),
        )

    async def list_upcoming_expirations(
        self,
        agent_fqn: str,
        within_days: int,
    ) -> list[Any]:
        certifications = (
            await self.recertification_service.repository.list_expiry_approaching_certifications(
                now=datetime.now(UTC),
                within_days=within_days,
            )
        )
        return [item for item in certifications if item.agent_id == agent_fqn]


class AgentOpsEvalAdapter:
    def __init__(
        self,
        *,
        eval_suite_service: Any,
        evaluation_repository: EvaluationRepository,
    ) -> None:
        self.eval_suite_service = eval_suite_service
        self.evaluation_repository = evaluation_repository

    async def get_latest_agent_score(self, agent_fqn: str, workspace_id: UUID) -> Any:
        del agent_fqn, workspace_id
        return None

    async def get_run_results(self, run_id: UUID) -> Any:
        return await self.eval_suite_service.get_run_summary(run_id)

    async def submit_to_ate(self, revision_id: UUID, eval_set_id: UUID, workspace_id: UUID) -> Any:
        del revision_id, eval_set_id, workspace_id
        return None

    async def get_human_grade_aggregate(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        window_days: int,
    ) -> Any:
        del agent_fqn, workspace_id, window_days
        return None

    async def resolve_default_ate_config(self, workspace_id: UUID) -> UUID | None:
        configs, _ = await self.evaluation_repository.list_ate_configs(
            workspace_id,
            page=1,
            page_size=1,
        )
        if not configs:
            return None
        return configs[0].id

    async def start_ate_run(
        self,
        *,
        ate_config_id: UUID,
        workspace_id: UUID,
        agent_fqn: str,
        candidate_revision_id: UUID,
    ) -> Any:
        config = await self.evaluation_repository.get_ate_config(ate_config_id, workspace_id)
        if config is None:
            return None
        pre_check_errors = _ate_pre_check(config)
        status = ATERunStatus.pre_check_failed if pre_check_errors else ATERunStatus.pending
        run = await self.evaluation_repository.create_ate_run(
            ATERun(
                workspace_id=workspace_id,
                ate_config_id=ate_config_id,
                agent_fqn=agent_fqn,
                agent_id=candidate_revision_id,
                status=status,
                pre_check_errors=pre_check_errors or None,
            )
        )
        return run


class AgentOpsPolicyAdapter:
    def __init__(self, *, policy_service: Any) -> None:
        self.policy_service = policy_service

    async def evaluate_conformance(
        self,
        agent_fqn: str,
        revision_id: UUID,
        workspace_id: UUID,
    ) -> Any:
        del agent_fqn, revision_id, workspace_id
        return {"passed": True, "violations": []}


class AgentOpsWorkflowAdapter:
    def __init__(self, *, workflow_service: Any) -> None:
        self.workflow_service = workflow_service

    async def find_workflows_using_agent(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> list[dict[str, Any]]:
        del agent_fqn, workspace_id
        return []


class AgentOpsRegistryAdapter:
    def __init__(
        self,
        *,
        session: AsyncSession,
        registry_service: Any | None = None,
    ) -> None:
        self.session = session
        self.registry_service = registry_service
        self.repository = RegistryRepository(session)

    async def get_agent_revision(self, agent_fqn: str, revision_id: UUID) -> Any:
        if self.registry_service is not None and hasattr(
            self.registry_service, "get_agent_revision"
        ):
            return await self.registry_service.get_agent_revision(agent_fqn, revision_id)
        revision = await self.repository.get_revision_by_id(revision_id)
        if revision is None:
            return None
        profile = await self.repository.get_agent_by_id_any(revision.agent_profile_id)
        if profile is None or profile.fqn != agent_fqn:
            return None
        return revision

    async def set_marketplace_visibility(
        self,
        agent_fqn: str,
        visible: bool,
        workspace_id: UUID,
    ) -> None:
        if self.registry_service is not None and hasattr(
            self.registry_service,
            "set_marketplace_visibility",
        ):
            await self.registry_service.set_marketplace_visibility(
                agent_fqn,
                visible,
                workspace_id,
            )
            return

    async def get_profile_state(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> dict[str, Any] | None:
        if self.registry_service is not None and hasattr(
            self.registry_service, "get_profile_state"
        ):
            return cast(
                dict[str, Any] | None,
                await self.registry_service.get_profile_state(agent_fqn, workspace_id),
            )

        profile = await self.repository.get_by_fqn(workspace_id, agent_fqn)
        if profile is None:
            return None
        revision = await self.repository.get_latest_revision(profile.id)
        return {
            "agent_profile_id": profile.id,
            "agent_fqn": profile.fqn,
            "workspace_id": profile.workspace_id,
            "revision_id": revision.id if revision is not None else None,
            "display_name": profile.display_name,
            "purpose": profile.purpose,
            "approach": profile.approach,
            "role_types": list(profile.role_types or []),
            "custom_role_description": profile.custom_role_description,
            "tags": list(profile.tags or []),
            "visibility_agents": list(profile.visibility_agents or []),
            "visibility_tools": list(profile.visibility_tools or []),
            "mcp_server_refs": list(profile.mcp_server_refs or []),
            "status": str(profile.status),
        }

    async def update_profile_fields(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        fields: dict[str, Any],
    ) -> dict[str, Any] | None:
        if self.registry_service is not None and hasattr(
            self.registry_service, "update_profile_fields"
        ):
            return cast(
                dict[str, Any] | None,
                await self.registry_service.update_profile_fields(agent_fqn, workspace_id, fields),
            )

        profile = await self.repository.get_by_fqn(workspace_id, agent_fqn)
        if profile is None:
            return None
        mutable_fields = {
            "display_name",
            "purpose",
            "approach",
            "role_types",
            "custom_role_description",
            "tags",
            "visibility_agents",
            "visibility_tools",
            "mcp_server_refs",
        }
        for name, value in fields.items():
            if name not in mutable_fields:
                continue
            setattr(profile, name, value)
        profile.needs_reindex = True
        await self.session.flush()
        return await self.get_profile_state(agent_fqn, workspace_id)

    async def list_active_agents(self, workspace_id: UUID | None = None) -> list[dict[str, Any]]:
        if self.registry_service is not None and hasattr(
            self.registry_service, "list_active_agents"
        ):
            return cast(
                list[dict[str, Any]],
                await self.registry_service.list_active_agents(workspace_id),
            )

        query = select(AgentProfile).where(AgentProfile.status == LifecycleStatus.published)
        if workspace_id is not None:
            query = query.where(AgentProfile.workspace_id == workspace_id)
        query = query.order_by(AgentProfile.created_at.asc(), AgentProfile.id.asc())

        result = await self.session.execute(query)
        profiles = list(result.scalars().all())
        targets: list[dict[str, Any]] = []
        for profile in profiles:
            revision = await self.repository.get_latest_revision(profile.id)
            if revision is None:
                continue
            targets.append(
                {
                    "agent_fqn": profile.fqn,
                    "workspace_id": profile.workspace_id,
                    "revision_id": revision.id,
                }
            )
        return targets

    async def create_candidate_revision(
        self,
        *,
        agent_fqn: str,
        base_revision_id: UUID,
        workspace_id: UUID,
        adjustments: list[dict[str, object]],
        actor_id: UUID,
    ) -> Any:
        base_revision = await self.get_agent_revision(agent_fqn, base_revision_id)
        if base_revision is None:
            return None
        manifest_snapshot = dict(getattr(base_revision, "manifest_snapshot", {}) or {})
        manifest_snapshot["agentops_adaptation"] = {
            "base_revision_id": str(base_revision_id),
            "adjustments": adjustments,
            "generated_at": datetime.now(UTC).isoformat(),
        }
        version = f"adapt-{uuid4().hex[:8]}"
        storage_key = f"{getattr(base_revision, 'storage_key', 'agentops/candidate')}.{version}"
        adjustment_summary = sorted(
            (item.get("rule_type"), item.get("action")) for item in adjustments
        )
        digest = hashlib.sha256(repr(adjustment_summary).encode("utf-8")).hexdigest()
        return await self.repository.insert_revision(
            revision_id=uuid4(),
            workspace_id=workspace_id,
            agent_profile_id=base_revision.agent_profile_id,
            version=version,
            sha256_digest=digest,
            storage_key=storage_key,
            manifest_snapshot=manifest_snapshot,
            uploaded_by=actor_id,
        )


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _get_redis(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


def _get_clickhouse(request: Request) -> AsyncClickHouseClient:
    return cast(AsyncClickHouseClient, request.app.state.clients["clickhouse"])


def _get_reasoning_client(request: Request) -> ReasoningEngineClient | None:
    return cast(ReasoningEngineClient | None, request.app.state.clients.get("reasoning_engine"))


def resolve_workspace_id(request: Request, current_user: dict[str, Any]) -> UUID:
    explicit = current_user.get("workspace_id") or request.headers.get("X-Workspace-ID")
    if explicit is not None:
        return UUID(str(explicit))
    roles = current_user.get("roles")
    if isinstance(roles, list):
        for role in roles:
            if isinstance(role, dict) and role.get("workspace_id"):
                return UUID(str(role["workspace_id"]))
    raise ValidationError("WORKSPACE_REQUIRED", "workspace_id is required")


async def get_agentops_workspace_id(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> UUID:
    return resolve_workspace_id(request, current_user)


def build_agentops_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    redis_client: AsyncRedisClient,
    clickhouse_client: AsyncClickHouseClient | Any | None,
    reasoning_client: ReasoningEngineClient | None,
) -> AgentOpsService:
    repository = AgentOpsRepository(session)
    event_publisher = AgentOpsEventPublisher(producer)
    governance_publisher = GovernanceEventPublisher(
        repository=repository,
        event_publisher=event_publisher,
    )
    trust_service = AgentOpsTrustAdapter(
        certification_service=build_certification_service(
            session=session,
            settings=settings,
            producer=producer,
        ),
        trust_tier_service=build_trust_tier_service(
            session=session,
            settings=settings,
            producer=producer,
        ),
        recertification_service=build_recertification_service(
            session=session,
            settings=settings,
            producer=producer,
        ),
    )
    eval_service = AgentOpsEvalAdapter(
        eval_suite_service=build_eval_suite_service(
            session=session,
            settings=settings,
            producer=producer,
        ),
        evaluation_repository=EvaluationRepository(session),
    )
    policy_service = AgentOpsPolicyAdapter(
        policy_service=build_policy_service(
            session=session,
            settings=settings,
            producer=producer,
            redis_client=cast(Any, redis_client),
            registry_service=None,
            workspaces_service=None,
            reasoning_client=cast(Any, reasoning_client),
        )
    )
    workflow_service = AgentOpsWorkflowAdapter(
        workflow_service=build_workflow_service(
            session=session,
            settings=settings,
            producer=producer,
            scheduler=None,
        )
    )
    registry_service = AgentOpsRegistryAdapter(
        session=session,
    )
    return AgentOpsService(
        settings=settings,
        repository=repository,
        event_publisher=event_publisher,
        governance_publisher=governance_publisher,
        trust_service=trust_service,
        eval_suite_service=eval_service,
        policy_service=policy_service,
        workflow_service=workflow_service,
        registry_service=registry_service,
        redis_client=redis_client,
        clickhouse_client=clickhouse_client,
    )


def _ate_pre_check(config: Any) -> list[dict[str, Any]]:
    scenarios = list(getattr(config, "scenarios", []) or [])
    errors: list[dict[str, Any]] = []
    if not scenarios:
        errors.append(
            {
                "code": "ATE_SCENARIOS_REQUIRED",
                "message": "At least one scenario is required",
            }
        )
    for index, scenario in enumerate(scenarios):
        for field in ("id", "name", "input_data", "expected_output"):
            if field not in scenario:
                errors.append(
                    {
                        "code": "ATE_SCENARIO_MISSING_FIELD",
                        "index": index,
                        "field": field,
                        "message": f"Scenario {index} is missing {field}",
                    }
                )
    return errors


async def get_agentops_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> AgentOpsService:
    return build_agentops_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        redis_client=_get_redis(request),
        clickhouse_client=_get_clickhouse(request),
        reasoning_client=_get_reasoning_client(request),
    )


AgentOpsServiceDep = Annotated[AgentOpsService, Depends(get_agentops_service)]
