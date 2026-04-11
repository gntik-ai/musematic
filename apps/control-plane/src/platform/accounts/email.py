from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

LOGGER = logging.getLogger(__name__)


async def send_verification_email(
    user_id: UUID,
    email: str,
    token: str,
    display_name: str,
    notification_client: Any | None = None,
) -> None:
    if notification_client is not None:
        send = getattr(notification_client, "send_verification_email", None)
        if callable(send):
            await send(user_id=user_id, email=email, token=token, display_name=display_name)
            return

    LOGGER.info(
        "Verification email queued",
        extra={
            "user_id": str(user_id),
            "email": email,
            "token": token,
            "display_name": display_name,
        },
    )


async def send_invitation_email(
    invitation_id: UUID,
    email: str,
    token: str,
    inviter_id: UUID,
    message: str | None,
    notification_client: Any | None = None,
) -> None:
    if notification_client is not None:
        send = getattr(notification_client, "send_invitation_email", None)
        if callable(send):
            await send(
                invitation_id=invitation_id,
                email=email,
                token=token,
                inviter_id=inviter_id,
                message=message,
            )
            return

    LOGGER.info(
        "Invitation email queued",
        extra={
            "invitation_id": str(invitation_id),
            "email": email,
            "token": token,
            "inviter_id": str(inviter_id),
            "invitee_message": message,
        },
    )
