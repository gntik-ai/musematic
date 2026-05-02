from __future__ import annotations

from platform.accounts import email as email_module
from uuid import uuid4

import pytest


class NotificationClientStub:
    def __init__(self) -> None:
        self.verification_calls: list[dict[str, object]] = []
        self.invitation_calls: list[dict[str, object]] = []

    async def send_verification_email(self, **kwargs) -> None:
        self.verification_calls.append(kwargs)

    async def send_invitation_email(self, **kwargs) -> None:
        self.invitation_calls.append(kwargs)


@pytest.mark.asyncio
async def test_send_verification_email_uses_notification_client_when_available() -> None:
    client = NotificationClientStub()

    await email_module.send_verification_email(
        user_id=uuid4(),
        email="user@example.com",
        token="token",
        display_name="Jane Smith",
        notification_client=client,
    )

    assert client.verification_calls[0]["email"] == "user@example.com"


@pytest.mark.asyncio
async def test_send_email_helpers_log_when_no_notification_client(capsys) -> None:
    invitation_id = uuid4()

    await email_module.send_verification_email(
        user_id=uuid4(),
        email="user@example.com",
        token="token",
        display_name="Jane Smith",
    )
    await email_module.send_invitation_email(
        invitation_id=invitation_id,
        email="invitee@example.com",
        token="invite-token",
        inviter_id=uuid4(),
        message="Welcome aboard",
    )

    output = capsys.readouterr().out
    assert "Verification email queued" in output
    assert "Invitation email queued" in output
