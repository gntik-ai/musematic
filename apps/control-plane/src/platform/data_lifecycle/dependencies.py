"""FastAPI dependency wiring for the data_lifecycle BC."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select, text

from platform.common.config import PlatformSettings
from platform.common.database import AsyncSessionLocal
from platform.data_lifecycle.cascade_dispatch.tenant_cascade import (
    dispatch_tenant_cascade,
)
from platform.data_lifecycle.cascade_dispatch.workspace_cascade import (
    dispatch_workspace_cascade,
)
from platform.data_lifecycle.exceptions import (
    DataLifecycleError,
    DefaultTenantCannotBeDeleted,
    TenantPendingDeletion,
    TypedConfirmationMismatch,
)
from platform.data_lifecycle.repository import DataLifecycleRepository
from platform.data_lifecycle.serializers.tenant import (
    build_default_tenant_serializers,
)
from platform.data_lifecycle.serializers.workspace import (
    build_default_workspace_serializers,
)
from platform.data_lifecycle.services.deletion_service import DeletionService
from platform.data_lifecycle.services.export_service import ExportService
from platform.tenants.models import Tenant
from platform.workspaces.models import Workspace


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_repository(
    session: AsyncSession = Depends(get_session),
) -> DataLifecycleRepository:
    return DataLifecycleRepository(session)


def get_export_service(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ExportService:
    settings: PlatformSettings = request.app.state.settings
    clients: dict[str, object] = request.app.state.clients
    return ExportService(
        repository=DataLifecycleRepository(session),
        settings=settings.data_lifecycle,
        object_storage=clients["object_storage"],  # type: ignore[arg-type]
        audit_chain=getattr(request.app.state, "audit_chain_service", None),
        event_producer=clients.get("kafka"),  # type: ignore[arg-type]
        redis_client=clients.get("redis"),  # type: ignore[arg-type]
        workspace_serializers=build_default_workspace_serializers(session=session),
        tenant_serializers=build_default_tenant_serializers(session=session),
    )


class _DirectWorkspaceMutator:
    """Adapter satisfying ``_WorkspaceStateMutator`` for the deletion service.

    Bypasses the WorkspacesService (which has its own membership /
    archive semantics) and operates directly on the workspaces table.
    Validation: the workspace exists, the caller is the owner, and the
    workspace is currently ``active`` or ``archived`` (NOT
    ``pending_deletion`` or ``deleted``).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_workspace_for_deletion(
        self, *, workspace_id: UUID, requested_by_user_id: UUID
    ) -> tuple[str, str]:
        workspace = await self._session.get(Workspace, workspace_id)
        if workspace is None:
            raise DataLifecycleError(f"workspace {workspace_id} not found")
        if str(workspace.owner_id) != str(requested_by_user_id):
            raise DataLifecycleError(
                "only the workspace owner may request deletion"
            )
        if workspace.status.value in {"pending_deletion", "deleted"}:
            raise DataLifecycleError(
                f"workspace {workspace_id} is already {workspace.status.value}"
            )
        return workspace.name, workspace.status.value

    async def set_workspace_status(
        self, *, workspace_id: UUID, status: str
    ) -> None:
        await self._session.execute(
            update(Workspace)
            .where(Workspace.id == workspace_id)
            .values(status=status)
        )


class _DirectTenantMutator:
    """Adapter satisfying ``_TenantStateMutator`` for the deletion service."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_tenant_for_deletion(
        self, *, tenant_id: UUID
    ) -> tuple[str, str, dict]:
        tenant = await self._session.get(Tenant, tenant_id)
        if tenant is None:
            raise DataLifecycleError(f"tenant {tenant_id} not found")
        if tenant.kind == "default":
            raise DefaultTenantCannotBeDeleted(
                "the platform default tenant cannot be deleted"
            )
        if tenant.status in {"pending_deletion", "deleted"}:
            raise TenantPendingDeletion(
                f"tenant {tenant_id} is already {tenant.status}"
            )
        return tenant.slug, tenant.status, dict(tenant.contract_metadata_json or {})

    async def set_tenant_status(self, *, tenant_id: UUID, status: str) -> None:
        # tenants.status CHECK accepts only active/suspended/pending_deletion,
        # so map "deleted" to a row deletion attempt elsewhere; in this MVP
        # we only flip pending_deletion / active.
        if status in {"active", "suspended", "pending_deletion"}:
            await self._session.execute(
                text("UPDATE tenants SET status = :s WHERE id = :id"),
                {"s": status, "id": str(tenant_id)},
            )


class _DirectSubscriptionGate:
    """Adapter satisfying ``_SubscriptionGate``.

    Reads the subscriptions table directly. ``trial``, ``active``, and
    ``past_due`` count as "still billable"; ``canceled`` /
    ``cancellation_pending`` / ``suspended`` do not block deletion.
    """

    BLOCKING_STATES = ("trial", "active", "past_due")

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def has_active_subscription(self, *, tenant_id: UUID) -> bool:
        result = await self._session.execute(
            text(
                """
                SELECT 1 FROM subscriptions
                WHERE tenant_id = :tenant_id
                  AND status = ANY(:blocking)
                LIMIT 1
                """
            ),
            {"tenant_id": str(tenant_id), "blocking": list(self.BLOCKING_STATES)},
        )
        return result.scalar_one_or_none() is not None


class _DirectTwoPAGate:
    """Adapter satisfying ``_TwoPAGate``.

    Delegates to the existing ``two_person_approval.service`` consume
    method via a fresh service instance scoped to the same session.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def consume_or_raise(
        self, *, challenge_id: UUID, requester_id: UUID
    ) -> dict:
        from platform.two_person_approval.service import TwoPersonApprovalService

        service = TwoPersonApprovalService(self._session)
        response, _payload = await service.consume_challenge(
            challenge_id=challenge_id, requester_id=requester_id
        )
        return {
            "challenge_id": str(challenge_id),
            "consumed_at": getattr(response, "consumed_at", None)
            and response.consumed_at.isoformat(),
        }


def get_deletion_service(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> DeletionService:
    settings: PlatformSettings = request.app.state.settings
    clients: dict[str, object] = request.app.state.clients

    cascade_orchestrator = getattr(request.app.state, "cascade_orchestrator", None)

    async def _dispatch_workspace(*, workspace_id, requested_by_user_id):
        if cascade_orchestrator is None:
            return {"errors": [], "store_results": []}
        return await dispatch_workspace_cascade(
            orchestrator=cascade_orchestrator,
            workspace_id=workspace_id,
            requested_by_user_id=requested_by_user_id,
        )

    async def _dispatch_tenant(*, tenant_id, requested_by_user_id):
        if cascade_orchestrator is None:
            return {"errors": [], "store_results": []}
        # Resolve tenant slug for DNS teardown leg.
        tenant = await session.get(Tenant, tenant_id)
        slug = tenant.slug if tenant is not None else str(tenant_id)
        return await dispatch_tenant_cascade(
            orchestrator=cascade_orchestrator,
            settings=settings,
            tenant_id=tenant_id,
            tenant_slug=slug,
            requested_by_user_id=requested_by_user_id,
            dns_teardown=getattr(request.app.state, "dns_teardown_service", None),
        )

    # Inject ExportService.request_tenant_export so the deletion service
    # can link a final-export job at phase_1 time without re-importing.
    export_service = get_export_service(request=request, session=session)

    async def _request_tenant_export(*, tenant_id, requested_by_user_id, correlation_ctx=None):
        return await export_service.request_tenant_export(
            tenant_id=tenant_id,
            requested_by_user_id=requested_by_user_id,
            correlation_ctx=correlation_ctx,
        )

    return DeletionService(
        repository=DataLifecycleRepository(session),
        settings=settings.data_lifecycle,
        workspace_mutator=_DirectWorkspaceMutator(session),
        audit_chain=getattr(request.app.state, "audit_chain_service", None),
        event_producer=clients.get("kafka"),  # type: ignore[arg-type]
        cascade_dispatcher=_dispatch_workspace,
        tenant_mutator=_DirectTenantMutator(session),
        subscription_gate=_DirectSubscriptionGate(session),
        two_pa_gate=_DirectTwoPAGate(session),
        tenant_cascade_dispatcher=_dispatch_tenant,
        export_request_handler=_request_tenant_export,
    )
