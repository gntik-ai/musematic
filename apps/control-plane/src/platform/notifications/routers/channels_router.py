from __future__ import annotations

from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.notifications.channel_router import AuditChainService
from platform.notifications.dependencies import (
    get_audit_chain_service,
    get_notifications_service,
)
from platform.notifications.schemas import (
    ChannelConfigCreate,
    ChannelConfigRead,
    ChannelConfigUpdate,
)
from platform.notifications.service import AlertService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

router = APIRouter(prefix="/notifications/channels", tags=["notifications-channels"])


class ChannelVerifyRequest(BaseModel):
    token: str = Field(min_length=1)


def _user_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


@router.get("", response_model=list[ChannelConfigRead])
async def list_channels(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: AlertService = Depends(get_notifications_service),
) -> list[ChannelConfigRead]:
    return await service.list_channel_configs(_user_id(current_user))


@router.post("", response_model=ChannelConfigRead, status_code=201)
async def create_channel(
    payload: ChannelConfigCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: AlertService = Depends(get_notifications_service),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> ChannelConfigRead:
    user_id = _user_id(current_user)
    channel = await service.create_channel_config(user_id, payload)
    await _append_audit(
        audit_chain,
        actor=user_id,
        subject=channel.id,
        user_id=user_id,
        action="created",
        before=None,
        after=channel.model_dump(mode="json"),
    )
    return channel


@router.patch("/{channel_id}", response_model=ChannelConfigRead)
async def update_channel(
    channel_id: UUID,
    payload: ChannelConfigUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: AlertService = Depends(get_notifications_service),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> ChannelConfigRead:
    user_id = _user_id(current_user)
    before = await _find_channel(service, user_id, channel_id)
    channel = await service.update_channel_config(user_id, channel_id, payload)
    await _append_audit(
        audit_chain,
        actor=user_id,
        subject=channel.id,
        user_id=user_id,
        action="updated",
        before=before.model_dump(mode="json"),
        after=channel.model_dump(mode="json"),
    )
    return channel


@router.delete("/{channel_id}", status_code=204)
async def delete_channel(
    channel_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: AlertService = Depends(get_notifications_service),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> None:
    user_id = _user_id(current_user)
    before = await _find_channel(service, user_id, channel_id)
    await service.delete_channel_config(user_id, channel_id)
    await _append_audit(
        audit_chain,
        actor=user_id,
        subject=channel_id,
        user_id=user_id,
        action="deleted",
        before=before.model_dump(mode="json"),
        after=None,
    )


@router.post("/{channel_id}/verify", response_model=ChannelConfigRead)
async def verify_channel(
    channel_id: UUID,
    payload: ChannelVerifyRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: AlertService = Depends(get_notifications_service),
) -> ChannelConfigRead:
    return await service.verify_channel_config(_user_id(current_user), channel_id, payload.token)


@router.post("/{channel_id}/resend-verification", response_model=ChannelConfigRead)
async def resend_channel_verification(
    channel_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: AlertService = Depends(get_notifications_service),
) -> ChannelConfigRead:
    return await service.resend_channel_verification(_user_id(current_user), channel_id)


async def _find_channel(
    service: AlertService,
    user_id: UUID,
    channel_id: UUID,
) -> ChannelConfigRead:
    return await service.get_channel_config_for_user(user_id, channel_id)


async def _append_audit(
    audit_chain: AuditChainService,
    *,
    actor: UUID,
    subject: UUID,
    user_id: UUID,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    await audit_chain.append(
        {
            "event": "notifications.channel.config.changed",
            "actor": str(actor),
            "subject": str(subject),
            "scope": {"user_id": str(user_id)},
            "action": action,
            "diff": {"before": before, "after": after},
            "occurred_at": datetime.now(UTC).isoformat(),
        }
    )
