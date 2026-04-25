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
    DeadLetterListItem,
    DeadLetterReplayBatchRequest,
    DeadLetterReplayBatchResponse,
    DeadLetterReplayRequest,
    DeadLetterResolveRequest,
    WebhookDeliveryRead,
)
from platform.notifications.webhooks_service import OutboundWebhookService
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query

router = APIRouter(prefix="/notifications/dead-letter", tags=["notifications-dead-letter"])


@router.get("", response_model=list[DeadLetterListItem])
async def list_dead_letters(
    workspace_id: UUID = Query(),
    webhook_id: UUID | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    reason: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: OutboundWebhookService = Depends(get_outbound_webhook_service),
) -> list[DeadLetterListItem]:
    _authorize_workspace(current_user, workspace_id)
    return await service.list_dead_letters(
        workspace_id,
        _filters(
            webhook_id=webhook_id,
            failure_reason=reason,
            since=since,
            until=until,
            limit=limit,
        ),
    )


@router.get("/{delivery_id}", response_model=DeadLetterListItem)
async def get_dead_letter(
    delivery_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: OutboundWebhookService = Depends(get_outbound_webhook_service),
) -> DeadLetterListItem:
    delivery = await service.get_dead_letter(delivery_id)
    assert delivery.workspace_id is not None
    _authorize_workspace(current_user, delivery.workspace_id)
    return delivery


@router.post("/{delivery_id}/replay", response_model=WebhookDeliveryRead)
async def replay_dead_letter(
    delivery_id: UUID,
    payload: DeadLetterReplayRequest | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: OutboundWebhookService = Depends(get_outbound_webhook_service),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> WebhookDeliveryRead:
    del payload
    actor_id = _actor_id(current_user)
    original = await service.get_dead_letter(delivery_id)
    assert original.workspace_id is not None
    _authorize_workspace(current_user, original.workspace_id)
    replay = await service.replay_dead_letter(delivery_id, actor_id=actor_id)
    await _append_audit(
        audit_chain,
        event="notifications.dead_letter.replayed",
        actor=actor_id,
        subject=delivery_id,
        workspace_id=original.workspace_id,
        payload={"dead_lettered_at": _iso(original.dead_lettered_at), "replay_id": str(replay.id)},
    )
    return replay


@router.post("/replay-batch", response_model=DeadLetterReplayBatchResponse)
async def replay_dead_letter_batch(
    payload: DeadLetterReplayBatchRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: OutboundWebhookService = Depends(get_outbound_webhook_service),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> DeadLetterReplayBatchResponse:
    actor_id = _actor_id(current_user)
    _authorize_workspace(current_user, payload.workspace_id)
    replayed = await service.replay_dead_letters(
        workspace_id=payload.workspace_id,
        actor_id=actor_id,
        filters=payload.model_dump(exclude={"workspace_id"}, exclude_none=True),
    )
    job_id = uuid4()
    await _append_audit(
        audit_chain,
        event="notifications.dead_letter.batch_replayed",
        actor=actor_id,
        subject=job_id,
        workspace_id=payload.workspace_id,
        payload={"replayed": len(replayed)},
    )
    return DeadLetterReplayBatchResponse(job_id=job_id, replayed=len(replayed))


@router.post("/{delivery_id}/resolve", response_model=WebhookDeliveryRead)
async def resolve_dead_letter(
    delivery_id: UUID,
    payload: DeadLetterResolveRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: OutboundWebhookService = Depends(get_outbound_webhook_service),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> WebhookDeliveryRead:
    actor_id = _actor_id(current_user)
    original = await service.get_dead_letter(delivery_id)
    assert original.workspace_id is not None
    _authorize_workspace(current_user, original.workspace_id)
    resolved = await service.resolve_dead_letter(
        delivery_id,
        actor_id=actor_id,
        resolution=payload.resolution,
    )
    await _append_audit(
        audit_chain,
        event="notifications.dead_letter.resolved",
        actor=actor_id,
        subject=delivery_id,
        workspace_id=original.workspace_id,
        payload={"resolution": payload.resolution},
    )
    return resolved


def _actor_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


def _role_names(current_user: dict[str, Any]) -> set[str]:
    roles = current_user.get("roles", [])
    names = {str(item.get("role")) for item in roles if isinstance(item, dict)}
    raw = current_user.get("role")
    if raw:
        names.add(str(raw))
    return names


def _authorize_workspace(current_user: dict[str, Any], workspace_id: UUID) -> None:
    roles = _role_names(current_user)
    if roles & {"superadmin", "auditor", "admin"}:
        return
    if roles & {"workspace_admin", "workspace_admin_user"}:
        claim_workspace_id = current_user.get("workspace_id")
        if claim_workspace_id is None:
            return
        if str(claim_workspace_id) == str(workspace_id):
            return
    raise AuthorizationError("DEAD_LETTER_FORBIDDEN", "Dead-letter access is forbidden")


def _filters(
    *,
    webhook_id: UUID | None,
    failure_reason: str | None,
    since: datetime | None,
    until: datetime | None,
    limit: int,
) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "webhook_id": webhook_id,
            "failure_reason": failure_reason,
            "since": since,
            "until": until,
            "limit": limit,
        }.items()
        if value is not None
    }


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


async def _append_audit(
    audit_chain: AuditChainService,
    *,
    event: str,
    actor: UUID,
    subject: UUID,
    workspace_id: UUID,
    payload: dict[str, Any],
) -> None:
    await audit_chain.append(
        {
            "event": event,
            "actor": str(actor),
            "subject": str(subject),
            "scope": {"workspace_id": str(workspace_id)},
            "payload": payload,
            "occurred_at": datetime.now(UTC).isoformat(),
        }
    )
