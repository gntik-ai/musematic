from __future__ import annotations

from platform.audit.dependencies import build_audit_chain_service
from platform.audit.service import AuditChainService
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.common.tagging.label_service import LabelService
from platform.common.tagging.repository import TaggingRepository
from platform.common.tagging.saved_view_service import SavedViewService
from platform.common.tagging.service import TaggingService
from platform.common.tagging.tag_service import TagService
from platform.common.tagging.visibility_resolver import VisibilityResolver
from platform.evaluation.models import EvaluationRun
from platform.fleets.models import Fleet
from platform.policies.models import PolicyPolicy
from platform.registry.models import AgentProfile, LifecycleStatus
from platform.trust.models import TrustCertification
from platform.workflows.models import WorkflowDefinition
from platform.workspaces.models import Membership, Workspace, WorkspaceStatus
from typing import Any, cast
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import String, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _requester_id(requester: Any) -> UUID | None:
    if isinstance(requester, dict):
        raw = requester.get("sub") or requester.get("user_id")
        return UUID(str(raw)) if raw is not None else None
    raw_id = getattr(requester, "id", None)
    return UUID(str(raw_id)) if raw_id is not None else None


async def _workspace_ids_for_user(session: AsyncSession, requester: Any) -> set[UUID]:
    user_id = _requester_id(requester)
    if user_id is None:
        return set()
    result = await session.execute(
        select(Membership.workspace_id)
        .join(Workspace, Workspace.id == Membership.workspace_id)
        .where(Membership.user_id == user_id, Workspace.status == WorkspaceStatus.active)
    )
    return {UUID(str(item)) for item in result.scalars().all()}


def build_visibility_resolver(
    session: AsyncSession,
    settings: PlatformSettings,
) -> VisibilityResolver:
    async def visible_workspaces(requester: Any) -> set[UUID]:
        return await _workspace_ids_for_user(session, requester)

    async def visible_agents(requester: Any) -> set[UUID]:
        workspace_ids = await _workspace_ids_for_user(session, requester)
        if not workspace_ids:
            return set()
        result = await session.execute(
            select(AgentProfile.id).where(
                AgentProfile.workspace_id.in_(workspace_ids),
                AgentProfile.status != LifecycleStatus.decommissioned,
            )
        )
        return {UUID(str(item)) for item in result.scalars().all()}

    async def visible_fleets(requester: Any) -> set[UUID]:
        workspace_ids = await _workspace_ids_for_user(session, requester)
        if not workspace_ids:
            return set()
        result = await session.execute(
            select(Fleet.id).where(
                Fleet.workspace_id.in_(workspace_ids),
                Fleet.deleted_at.is_(None),
            )
        )
        return {UUID(str(item)) for item in result.scalars().all()}

    async def visible_workflows(requester: Any) -> set[UUID]:
        workspace_ids = await _workspace_ids_for_user(session, requester)
        if not workspace_ids:
            return set()
        result = await session.execute(
            select(WorkflowDefinition.id).where(WorkflowDefinition.workspace_id.in_(workspace_ids))
        )
        return {UUID(str(item)) for item in result.scalars().all()}

    async def visible_policies(requester: Any) -> set[UUID]:
        workspace_ids = await _workspace_ids_for_user(session, requester)
        if not workspace_ids:
            return set()
        result = await session.execute(
            select(PolicyPolicy.id).where(
                (PolicyPolicy.workspace_id.in_(workspace_ids))
                | (PolicyPolicy.workspace_id.is_(None))
            )
        )
        return {UUID(str(item)) for item in result.scalars().all()}

    async def visible_certifications(requester: Any) -> set[UUID]:
        workspace_ids = await _workspace_ids_for_user(session, requester)
        if not workspace_ids:
            return set()
        result = await session.execute(
            select(TrustCertification.id)
            .join(AgentProfile, TrustCertification.agent_id == sql_cast(AgentProfile.id, String))
            .where(AgentProfile.workspace_id.in_(workspace_ids))
        )
        return {UUID(str(item)) for item in result.scalars().all()}

    async def visible_evaluation_runs(requester: Any) -> set[UUID]:
        workspace_ids = await _workspace_ids_for_user(session, requester)
        if not workspace_ids:
            return set()
        result = await session.execute(
            select(EvaluationRun.id).where(EvaluationRun.workspace_id.in_(workspace_ids))
        )
        return {UUID(str(item)) for item in result.scalars().all()}

    return VisibilityResolver(
        providers={
            "workspace": visible_workspaces,
            "agent": visible_agents,
            "fleet": visible_fleets,
            "workflow": visible_workflows,
            "policy": visible_policies,
            "certification": visible_certifications,
            "evaluation_run": visible_evaluation_runs,
        },
        max_visible_ids=settings.tagging.cross_entity_search_max_visible_ids,
    )


def build_tag_service(
    session: AsyncSession,
    settings: PlatformSettings,
    audit_chain: AuditChainService | None,
) -> TagService:
    visibility_resolver = build_visibility_resolver(session, settings)

    async def entity_access_check(
        entity_type: str,
        entity_id: UUID,
        requester: Any,
        action: str,
    ) -> bool:
        del action
        visible = await visibility_resolver.resolve_visible_entity_ids(requester, [entity_type])
        return entity_id in visible.get(entity_type, set())

    return TagService(
        TaggingRepository(session),
        audit_chain=audit_chain,
        visibility_resolver=visibility_resolver,
        entity_access_check=entity_access_check,
        max_tags_per_entity=50,
    )


async def get_visibility_resolver(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> VisibilityResolver:
    return build_visibility_resolver(session, _get_settings(request))


async def get_tag_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> TagService:
    settings = _get_settings(request)
    producer = _get_producer(request)
    return build_tag_service(
        session,
        settings,
        build_audit_chain_service(session, settings, producer),
    )


async def get_label_service(
    session: AsyncSession = Depends(get_db),
) -> LabelService:
    return LabelService(TaggingRepository(session))


async def get_saved_view_service(
    session: AsyncSession = Depends(get_db),
) -> SavedViewService:
    return SavedViewService(TaggingRepository(session))


async def get_tagging_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> TaggingService:
    settings = _get_settings(request)
    producer = _get_producer(request)
    repo = TaggingRepository(session)
    visibility_resolver = build_visibility_resolver(session, settings)

    async def entity_access_check(
        entity_type: str,
        entity_id: UUID,
        requester: Any,
        action: str,
    ) -> bool:
        del action
        visible = await visibility_resolver.resolve_visible_entity_ids(requester, [entity_type])
        return entity_id in visible.get(entity_type, set())

    return TaggingService(
        TagService(
            repo,
            audit_chain=build_audit_chain_service(session, settings, producer),
            visibility_resolver=visibility_resolver,
            entity_access_check=entity_access_check,
            max_tags_per_entity=50,
        ),
        LabelService(repo),
        SavedViewService(repo),
    )


async def get_label_expression_evaluator() -> None:
    return None


async def get_label_expression_cache() -> None:
    return None
