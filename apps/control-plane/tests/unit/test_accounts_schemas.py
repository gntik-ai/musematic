from __future__ import annotations

from platform.accounts.schemas import (
    AcceptInvitationRequest,
    CreateInvitationRequest,
    RegisterRequest,
    VerifyEmailRequest,
)
from platform.auth.schemas import RoleType

import pytest
from pydantic import ValidationError


def test_register_request_normalizes_email_and_accepts_strong_password() -> None:
    payload = RegisterRequest(
        email="  USER@Example.COM ",
        display_name="Jane Smith",
        password="StrongP@ssw0rd!",
    )

    assert payload.email == "user@example.com"


@pytest.mark.parametrize(
    "password",
    [
        "short",
        "alllowercase123!",
        "ALLUPPERCASE123!",
        "NoDigitsHere!!",
        "NoSpecial12345",
    ],
)
def test_register_request_rejects_weak_passwords(password: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="user@example.com",
            display_name="Jane Smith",
            password=password,
        )


def test_accept_invitation_request_enforces_password_strength() -> None:
    with pytest.raises(ValidationError):
        AcceptInvitationRequest(
            token="invite-token",
            display_name="Jane Smith",
            password="weakpassword",
        )


def test_verify_email_request_rejects_empty_token() -> None:
    with pytest.raises(ValidationError):
        VerifyEmailRequest(token="")


def test_create_invitation_request_normalizes_email_and_requires_roles() -> None:
    payload = CreateInvitationRequest(
        email="  Invitee@Example.COM ",
        roles=[RoleType.VIEWER],
    )

    assert payload.email == "invitee@example.com"

    with pytest.raises(ValidationError):
        CreateInvitationRequest(email="invitee@example.com", roles=[])
