from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.common.exceptions import AuthorizationError
from platform.security_compliance.models import JitApproverPolicy, JitCredentialGrant
from platform.security_compliance.services.jit_service import JitService
from uuid import UUID, uuid4

import jwt
import pytest


class FakeRepository:
    def __init__(self) -> None:
        self.session = self
        self.grants: dict[UUID, JitCredentialGrant] = {}
        self.policies = [
            JitApproverPolicy(
                operation_pattern="customer_data:*",
                required_roles=["security_admin"],
                min_approvers=2,
                max_expiry_minutes=15,
            ),
            JitApproverPolicy(
                operation_pattern="deploy:*",
                required_roles=["platform_admin"],
                min_approvers=1,
                max_expiry_minutes=60,
            ),
        ]
        for policy in self.policies:
            policy.id = uuid4()

    async def flush(self) -> None:
        return None

    async def add(self, item: JitCredentialGrant) -> JitCredentialGrant:
        item.id = uuid4()
        self.grants[item.id] = item
        return item

    async def get_jit_grant(self, grant_id: UUID) -> JitCredentialGrant | None:
        return self.grants.get(grant_id)

    async def list_jit_grants(self, user_id: UUID | None = None) -> list[JitCredentialGrant]:
        return [item for item in self.grants.values() if user_id is None or item.user_id == user_id]

    async def list_jit_policies(self) -> list[JitApproverPolicy]:
        return self.policies


def _service(repository: FakeRepository) -> JitService:
    settings = PlatformSettings(
        auth={"jwt_secret_key": "a" * 32, "jwt_algorithm": "HS256"},
    )
    return JitService(repository, settings)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_jit_request_and_peer_approval_issues_jwt() -> None:
    repository = FakeRepository()
    service = _service(repository)
    requester = uuid4()
    grant, policy = await service.request_grant(
        user_id=requester,
        operation="deploy:prod",
        purpose="Deploy production hotfix SEC-1234",
        requested_expiry_minutes=30,
    )

    approved, token = await service.approve_grant(
        grant_id=grant.id,
        approver_id=uuid4(),
        approver_roles={"platform_admin"},
    )
    claims = jwt.decode(token, "a" * 32, algorithms=["HS256"])

    assert policy.min_approvers == 1
    assert approved.status == "approved"
    assert claims["jti"] == str(grant.id)
    assert claims["sub"] == str(requester)


@pytest.mark.asyncio
async def test_jit_self_approval_and_wrong_role_are_rejected() -> None:
    service = _service(FakeRepository())
    requester = uuid4()
    grant, _ = await service.request_grant(
        user_id=requester,
        operation="deploy:prod",
        purpose="Deploy production hotfix SEC-1234",
        requested_expiry_minutes=30,
    )

    with pytest.raises(AuthorizationError):
        await service.approve_grant(
            grant_id=grant.id,
            approver_id=requester,
            approver_roles={"platform_admin"},
        )
    with pytest.raises(AuthorizationError):
        await service.approve_grant(
            grant_id=grant.id,
            approver_id=uuid4(),
            approver_roles={"workspace_admin"},
        )


@pytest.mark.asyncio
async def test_jit_revoke_and_usage_audit() -> None:
    service = _service(FakeRepository())
    grant, _ = await service.request_grant(
        user_id=uuid4(),
        operation="deploy:prod",
        purpose="Deploy production hotfix SEC-1234",
        requested_expiry_minutes=30,
    )

    await service.record_usage(
        grant.id,
        operation="deploy:prod",
        target="prod",
        outcome="allowed",
    )
    revoked = await service.revoke_grant(grant.id, revoked_by=uuid4())

    assert revoked.status == "revoked"
    assert revoked.usage_audit[-1]["outcome"] == "allowed"


@pytest.mark.asyncio
async def test_customer_data_policy_requires_two_approvers() -> None:
    service = _service(FakeRepository())
    requester = uuid4()

    grant, policy = await service.request_grant(
        user_id=requester,
        operation="customer_data:read",
        purpose="Investigate customer support incident SEC-1234",
        requested_expiry_minutes=10,
    )
    first, first_token = await service.approve_grant(
        grant_id=grant.id,
        approver_id=uuid4(),
        approver_roles={"security_admin"},
    )
    first_status = first.status
    second, second_token = await service.approve_grant(
        grant_id=grant.id,
        approver_id=uuid4(),
        approver_roles={"security_admin"},
    )

    assert policy.min_approvers == 2
    assert first_status == "pending"
    assert first_token == ""
    assert second.status == "approved"
    assert second_token
