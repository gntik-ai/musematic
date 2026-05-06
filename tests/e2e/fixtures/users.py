"""UPD-054 (107) — Synthetic-user fixture for SaaS-pass journeys.

Creates users via the public accounts API (signup or admin-invite),
optionally enrolls MFA, returns a ``TestUser`` handle. Email aliases
under the ``.invalid`` TLD (RFC 2606) so addresses are non-deliverable.

Contract: see specs/107-saas-e2e-journeys/contracts/journey-template.md §
"Sub-scenario pattern"; data model: data-model.md § users.py.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import pyotp
import pytest

if TYPE_CHECKING:
    from .http_client import AuthenticatedAsyncClient
    from .tenants import TestTenant


__all__ = [
    "TestUser",
    "synthetic_user",
    "users",
]


Role = Literal["tenant_admin", "workspace_owner", "member", "viewer"]


@dataclass(frozen=True)
class TestUser:
    """Test-fixture handle for a synthetic user bound to a tenant."""

    user_id: uuid.UUID
    tenant_slug: str
    email: str
    role: Role
    mfa_enrolled: bool
    mfa_secret: str | None
    auth_token: str

    def totp_now(self) -> str:
        """Return the current 6-digit TOTP for an MFA-enrolled user."""
        if not self.mfa_secret:
            raise ValueError(f"User {self.email} has no MFA secret")
        return pyotp.TOTP(self.mfa_secret).now()


def _generate_email(*, tenant_slug: str, role: Role) -> str:
    """Email under the .invalid TLD per RFC 2606 — non-deliverable."""
    return f"e2e-{tenant_slug}-{role}-{uuid.uuid4().hex[:8]}@e2e.musematic-test.invalid"


@asynccontextmanager
async def synthetic_user(
    *,
    client: "AuthenticatedAsyncClient",
    tenant: "TestTenant",
    role: Role = "member",
    mfa_enrolled: bool = False,
    password: str = "E2eTest!Password1",
) -> AsyncIterator[TestUser]:
    """Create a synthetic user in ``tenant`` with the requested role.

    Uses the admin-invite path (`POST /api/v1/admin/tenants/{slug}/invite`)
    because journeys typically need users WITHIN an Enterprise tenant
    rather than going through the public-signup flow. For users created
    via public signup, see ``synthetic_signup_user``.
    """
    email = _generate_email(tenant_slug=tenant.slug, role=role)
    invite_response = await client.post(
        f"/api/v1/admin/tenants/{tenant.slug}/invite",
        json={"email": email, "role": role},
    )
    if invite_response.status_code not in {200, 201, 202}:
        raise RuntimeError(
            f"invite failed: {invite_response.status_code} {invite_response.text}"
        )
    invite_token = invite_response.json().get("invite_token", "")

    # Accept the invite (creates the user record + sets the password).
    accept_response = await client.post(
        "/api/v1/auth/accept-invite",
        json={"invite_token": invite_token, "password": password},
    )
    if accept_response.status_code not in {200, 201}:
        raise RuntimeError(
            f"accept-invite failed: {accept_response.status_code} {accept_response.text}"
        )
    accept_payload = accept_response.json()
    user_id = uuid.UUID(accept_payload["user_id"])
    auth_token = accept_payload["access_token"]

    mfa_secret: str | None = None
    if mfa_enrolled:
        # Begin MFA enrollment, capture the secret, confirm with a TOTP code.
        begin = await client.post(
            "/api/v1/auth/mfa/totp/begin",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        if begin.status_code != 200:
            raise RuntimeError(
                f"mfa begin failed: {begin.status_code} {begin.text}"
            )
        mfa_secret = begin.json()["secret"]
        confirm = await client.post(
            "/api/v1/auth/mfa/totp/confirm",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"code": pyotp.TOTP(mfa_secret).now()},
        )
        if confirm.status_code != 200:
            raise RuntimeError(
                f"mfa confirm failed: {confirm.status_code} {confirm.text}"
            )

    yield TestUser(
        user_id=user_id,
        tenant_slug=tenant.slug,
        email=email,
        role=role,
        mfa_enrolled=mfa_enrolled,
        mfa_secret=mfa_secret,
        auth_token=auth_token,
    )

    # Tenant teardown handles user cleanup (cascade); no per-user delete here.


@pytest.fixture
async def users() -> AsyncIterator[None]:
    """Pytest fixture binding ``synthetic_user`` into the test scope.

    Like ``tenants``, this is a no-op shim — the journey uses the async-CM
    directly. Kept so the import surface in conftest.py is symmetric with
    the other SaaS-pass fixtures.
    """
    yield
