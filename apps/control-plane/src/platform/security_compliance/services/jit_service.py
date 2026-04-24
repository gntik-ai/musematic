from __future__ import annotations

from datetime import timedelta
from fnmatch import fnmatch
from platform.audit.service import AuditChainService
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.producer import EventProducer
from platform.common.exceptions import AuthorizationError, NotFoundError, ValidationError
from platform.security_compliance.events import (
    JitIssuedPayload,
    JitRevokedPayload,
    publish_security_compliance_event,
)
from platform.security_compliance.models import JitApproverPolicy, JitCredentialGrant
from platform.security_compliance.repository import SecurityComplianceRepository
from platform.security_compliance.services._shared import append_audit, correlation, utcnow
from typing import Any
from uuid import UUID

import jwt


class JitService:
    def __init__(
        self,
        repository: SecurityComplianceRepository,
        settings: PlatformSettings,
        *,
        redis_client: AsyncRedisClient | None = None,
        producer: EventProducer | None = None,
        audit_chain: AuditChainService | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.redis_client = redis_client
        self.producer = producer
        self.audit_chain = audit_chain

    async def request_grant(
        self,
        *,
        user_id: UUID,
        operation: str,
        purpose: str,
        requested_expiry_minutes: int,
    ) -> tuple[JitCredentialGrant, JitApproverPolicy]:
        policy = await self.resolve_policy(operation)
        if requested_expiry_minutes > policy.max_expiry_minutes:
            raise ValidationError("JIT_EXPIRY_TOO_LONG", "Requested expiry exceeds policy")
        grant = await self.repository.add(
            JitCredentialGrant(
                user_id=user_id,
                operation=operation,
                purpose=purpose,
                status="pending",
                usage_audit=[
                    {
                        "timestamp": utcnow().isoformat(),
                        "operation": "requested",
                        "requested_expiry_minutes": requested_expiry_minutes,
                    }
                ],
            )
        )
        return grant, policy

    async def approve_grant(
        self,
        *,
        grant_id: UUID,
        approver_id: UUID,
        approver_roles: set[str],
    ) -> tuple[JitCredentialGrant, str]:
        grant = await self._get(grant_id)
        policy = await self.resolve_policy(grant.operation)
        if grant.user_id == approver_id:
            raise AuthorizationError("TWO_PERSON_APPROVAL_REQUIRED", "Requester cannot approve")
        if not (approver_roles & set(policy.required_roles)):
            raise AuthorizationError("PERMISSION_DENIED", "Approver lacks required role")
        now = utcnow()
        approvals = {
            str(item.get("approver_id"))
            for item in grant.usage_audit
            if item.get("operation") == "approved" and item.get("approver_id")
        }
        approvals.add(str(approver_id))
        grant.usage_audit = [
            *grant.usage_audit,
            {
                "timestamp": now.isoformat(),
                "operation": "approved",
                "approver_id": str(approver_id),
                "approvals": sorted(approvals),
                "min_approvers": policy.min_approvers,
            },
        ]
        if len(approvals) < policy.min_approvers:
            await self.repository.session.flush()
            return grant, ""
        grant.status = "approved"
        grant.approved_by = approver_id
        grant.approved_at = now
        grant.issued_at = now
        grant.expires_at = now + timedelta(minutes=policy.max_expiry_minutes)
        token = self._jwt(grant)
        await self.repository.session.flush()
        await publish_security_compliance_event(
            "security.jit.issued",
            JitIssuedPayload(
                grant_id=grant.id,
                user_id=grant.user_id,
                operation=grant.operation,
                expires_at=grant.expires_at,
            ),
            correlation(),
            self.producer,
            key=str(grant.id),
        )
        await append_audit(
            self.audit_chain,
            grant.id,
            "security_compliance",
            {"event": "jit.issued", "grant_id": grant.id, "operation": grant.operation},
        )
        return grant, token

    async def reject_grant(self, grant_id: UUID, *, reason: str) -> JitCredentialGrant:
        grant = await self._get(grant_id)
        grant.status = "rejected"
        grant.usage_audit = [
            *grant.usage_audit,
            {"timestamp": utcnow().isoformat(), "reason": reason},
        ]
        await self.repository.session.flush()
        return grant

    async def revoke_grant(self, grant_id: UUID, *, revoked_by: UUID) -> JitCredentialGrant:
        grant = await self._get(grant_id)
        grant.status = "revoked"
        grant.revoked_by = revoked_by
        grant.revoked_at = utcnow()
        if self.redis_client is not None:
            await self.redis_client.set(f"jit:revoked:{grant.id}", b"1", ttl=86400)
        await self.repository.session.flush()
        await publish_security_compliance_event(
            "security.jit.revoked",
            JitRevokedPayload(grant_id=grant.id, user_id=grant.user_id, revoked_by=revoked_by),
            correlation(),
            self.producer,
            key=str(grant.id),
        )
        await append_audit(
            self.audit_chain,
            grant.id,
            "security_compliance",
            {"event": "jit.revoked", "grant_id": grant.id, "revoked_by": revoked_by},
        )
        return grant

    async def record_usage(
        self,
        grant_id: UUID,
        *,
        operation: str,
        target: str,
        outcome: str,
    ) -> JitCredentialGrant:
        grant = await self._get(grant_id)
        grant.usage_audit = [
            *grant.usage_audit,
            {
                "timestamp": utcnow().isoformat(),
                "operation": operation,
                "target": target,
                "outcome": outcome,
            },
        ]
        await self.repository.session.flush()
        return grant

    async def list_grants(self, user_id: UUID | None = None) -> list[JitCredentialGrant]:
        return await self.repository.list_jit_grants(user_id)

    async def list_policies(self) -> list[JitApproverPolicy]:
        return await self.repository.list_jit_policies()

    async def resolve_policy(self, operation: str) -> JitApproverPolicy:
        policies = await self.repository.list_jit_policies()
        for policy in policies:
            if fnmatch(operation, policy.operation_pattern):
                return policy
        raise ValidationError("JIT_POLICY_NOT_FOUND", "No JIT policy matches operation")

    async def _get(self, grant_id: UUID) -> JitCredentialGrant:
        grant = await self.repository.get_jit_grant(grant_id)
        if grant is None:
            raise NotFoundError("JIT_GRANT_NOT_FOUND", "JIT grant not found")
        return grant

    def _jwt(self, grant: JitCredentialGrant) -> str:
        if grant.expires_at is None:
            raise ValidationError("JIT_EXPIRY_MISSING", "JIT grant expiry missing")
        payload: dict[str, Any] = {
            "sub": str(grant.user_id),
            "purpose": f"{grant.operation}:{grant.purpose}",
            "jti": str(grant.id),
            "iat": int(utcnow().timestamp()),
            "exp": int(grant.expires_at.timestamp()),
            "iss": "musematic",
            "type": "access",
            "identity_type": "user",
            "roles": [{"role": "jit", "workspace_id": None}],
        }
        return jwt.encode(
            payload, self.settings.auth.signing_key, algorithm=self.settings.auth.jwt_algorithm
        )
