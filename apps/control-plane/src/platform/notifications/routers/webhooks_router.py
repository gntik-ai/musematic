from __future__ import annotations

from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import AuthorizationError
from platform.notifications.channel_router import AuditChainService
from platform.notifications.dependencies import (
    get_audit_chain_service,
    get_outbound_webhook_service,
)
from platform.notifications.schemas import (
    OutboundWebhookCreate,
    OutboundWebhookCreateResponse,
    OutboundWebhookRead,
    OutboundWebhookUpdate,
    WebhookDeliveryRead,
)
from platform.notifications.webhooks_service import OutboundWebhookService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

router = APIRouter(prefix="/notifications/webhooks", tags=["notifications-webhooks"])


def _actor_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


def _role_names(current_user: dict[str, Any]) -> set[str]:
    roles = current_user.get("roles", [])
    return {str(item.get("role")) for item in roles if isinstance(item, dict)}


def _require_workspace_admin(current_user: dict[str, Any]) -> None:
    allowed_roles = {"workspace_admin", "workspace_admin_user", "admin", "superadmin"}
    if _role_names(current_user) & allowed_roles:
        return
    raise AuthorizationError("WEBHOOK_FORBIDDEN", "Workspace admin access is required")


@router.post("", response_model=OutboundWebhookCreateResponse, status_code=201)
async def create_webhook(
    payload: OutboundWebhookCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: OutboundWebhookService = Depends(get_outbound_webhook_service),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> OutboundWebhookCreateResponse:
    _require_workspace_admin(current_user)
    actor_id = _actor_id(current_user)
    created = await service.create(payload, actor_id=actor_id)
    await _append_audit(
        audit_chain,
        event="notifications.webhook.registered",
        actor=actor_id,
        subject=created.id,
        workspace_id=created.workspace_id,
        before=None,
        after=_without_secret(created),
    )
    return created


@router.get("", response_model=list[OutboundWebhookRead])
async def list_webhooks(
    workspace_id: UUID = Query(),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: OutboundWebhookService = Depends(get_outbound_webhook_service),
) -> list[OutboundWebhookRead]:
    _require_workspace_admin(current_user)
    return await service.list(workspace_id)


@router.get("/{webhook_id}", response_model=OutboundWebhookRead)
async def get_webhook(
    webhook_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: OutboundWebhookService = Depends(get_outbound_webhook_service),
) -> OutboundWebhookRead:
    _require_workspace_admin(current_user)
    return await service.get(webhook_id)


@router.patch("/{webhook_id}", response_model=OutboundWebhookRead)
async def update_webhook(
    webhook_id: UUID,
    payload: OutboundWebhookUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: OutboundWebhookService = Depends(get_outbound_webhook_service),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> OutboundWebhookRead:
    _require_workspace_admin(current_user)
    actor_id = _actor_id(current_user)
    before = await service.get(webhook_id)
    updated = await service.update(webhook_id, payload)
    await _append_audit(
        audit_chain,
        event=(
            "notifications.webhook.deactivated"
            if before.active and not updated.active
            else "notifications.webhook.updated"
        ),
        actor=actor_id,
        subject=updated.id,
        workspace_id=updated.workspace_id,
        before=before.model_dump(mode="json"),
        after=updated.model_dump(mode="json"),
    )
    return updated


@router.post("/{webhook_id}/rotate-secret", response_model=OutboundWebhookRead)
async def rotate_webhook_secret(
    webhook_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: OutboundWebhookService = Depends(get_outbound_webhook_service),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> OutboundWebhookRead:
    _require_workspace_admin(current_user)
    actor_id = _actor_id(current_user)
    before = await service.get(webhook_id)
    rotated = await service.rotate_secret(webhook_id)
    await _append_audit(
        audit_chain,
        event="notifications.webhook.rotated",
        actor=actor_id,
        subject=rotated.id,
        workspace_id=rotated.workspace_id,
        before=before.model_dump(mode="json"),
        after=rotated.model_dump(mode="json"),
    )
    return rotated


@router.delete("/{webhook_id}", response_model=OutboundWebhookRead)
async def delete_webhook(
    webhook_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: OutboundWebhookService = Depends(get_outbound_webhook_service),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> OutboundWebhookRead:
    _require_workspace_admin(current_user)
    actor_id = _actor_id(current_user)
    before = await service.get(webhook_id)
    deactivated = await service.deactivate(webhook_id)
    await _append_audit(
        audit_chain,
        event="notifications.webhook.deactivated",
        actor=actor_id,
        subject=deactivated.id,
        workspace_id=deactivated.workspace_id,
        before=before.model_dump(mode="json"),
        after=deactivated.model_dump(mode="json"),
    )
    return deactivated


@router.post("/{webhook_id}/test", response_model=WebhookDeliveryRead)
async def send_test_webhook(
    webhook_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: OutboundWebhookService = Depends(get_outbound_webhook_service),
) -> WebhookDeliveryRead:
    _require_workspace_admin(current_user)
    return await service.send_test_event(webhook_id, actor_id=_actor_id(current_user))


def _without_secret(response: OutboundWebhookCreateResponse) -> dict[str, Any]:
    data = response.model_dump(mode="json")
    data.pop("signing_secret", None)
    return data


async def _append_audit(
    audit_chain: AuditChainService,
    *,
    event: str,
    actor: UUID,
    subject: UUID,
    workspace_id: UUID,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    await audit_chain.append(
        {
            "event": event,
            "actor": str(actor),
            "subject": str(subject),
            "scope": {"workspace_id": str(workspace_id)},
            "diff": {"before": before, "after": after},
            "occurred_at": datetime.now(UTC).isoformat(),
        }
    )
