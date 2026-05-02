"""Cross-tenant membership listing for UPD-048 FR-020 through FR-023.

The router injects `platform.common.database.get_platform_staff_session`; this service keeps
the BYPASSRLS session explicit so cross-tenant fanout remains scoped to this use case.
"""

from __future__ import annotations

import json
from platform.accounts.schemas import MembershipEntry
from platform.audit.service import AuditChainService
from platform.common.config import PlatformSettings
from platform.common.tenant_context import current_tenant
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class MembershipsService:
    def __init__(
        self,
        *,
        platform_staff_session: AsyncSession,
        settings: PlatformSettings,
        audit_chain: AuditChainService | None = None,
    ) -> None:
        self.session = platform_staff_session
        self.settings = settings
        self.audit_chain = audit_chain

    async def list_for_user(self, authenticated_user: dict[str, Any]) -> list[MembershipEntry]:
        email = await self._resolve_email(authenticated_user)
        current_tenant_id = self._current_tenant_id(authenticated_user)
        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT
                        u.id AS user_id,
                        u.tenant_id AS tenant_id,
                        t.slug AS tenant_slug,
                        t.kind AS tenant_kind,
                        t.display_name AS tenant_display_name,
                        COALESCE(
                            MAX(ur.role),
                            MAX(m.role),
                            'member'
                        ) AS role
                    FROM users u
                    JOIN tenants t ON t.id = u.tenant_id
                    LEFT JOIN user_roles ur ON ur.user_id = u.id
                    LEFT JOIN memberships m ON m.user_id = u.id
                    WHERE lower(u.email) = lower(:email)
                      AND u.status = 'active'
                    GROUP BY u.id, u.tenant_id, t.slug, t.kind, t.display_name
                    ORDER BY t.kind ASC, t.display_name ASC
                    """
                ),
                {"email": email},
            )
        ).mappings()
        memberships = [
            MembershipEntry(
                tenant_id=UUID(str(row["tenant_id"])),
                tenant_slug=str(row["tenant_slug"]),
                tenant_kind=str(row["tenant_kind"]),
                tenant_display_name=str(row["tenant_display_name"]),
                user_id_within_tenant=UUID(str(row["user_id"])),
                role=None if row["role"] is None else str(row["role"]),
                is_current_tenant=str(row["tenant_id"]) == str(current_tenant_id),
                login_url=self._login_url(str(row["tenant_slug"])),
            )
            for row in rows
        ]
        await self._append_audit(
            current_tenant_id,
            {
                "email_hash_scope": "authenticated_user",
                "membership_count": len(memberships),
                "actor_user_id": str(authenticated_user.get("sub") or ""),
            },
        )
        return memberships

    async def _resolve_email(self, authenticated_user: dict[str, Any]) -> str:
        email = authenticated_user.get("email")
        if isinstance(email, str) and email:
            return email.lower()
        user_id = UUID(str(authenticated_user["sub"]))
        row = (
            await self.session.execute(
                text("SELECT email FROM users WHERE id = :user_id"),
                {"user_id": str(user_id)},
            )
        ).mappings().first()
        if row is None:
            return ""
        return str(row["email"]).lower()

    def _current_tenant_id(self, authenticated_user: dict[str, Any]) -> UUID:
        tenant = current_tenant.get(None)
        if tenant is not None:
            return tenant.id
        raw = authenticated_user.get("tenant_id")
        if raw is not None:
            return UUID(str(raw))
        return UUID("00000000-0000-0000-0000-000000000001")

    def _login_url(self, tenant_slug: str) -> str:
        subdomain = "app" if tenant_slug == "default" else tenant_slug
        return f"https://{subdomain}.{self.settings.PLATFORM_DOMAIN}/login"

    async def _append_audit(self, tenant_id: UUID, payload: dict[str, object]) -> None:
        if self.audit_chain is None:
            return
        canonical_payload = {"tenant_id": str(tenant_id), **payload}
        canonical = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        await self.audit_chain.append(
            uuid4(),
            "accounts.memberships",
            canonical,
            event_type="accounts.memberships.listed",
            actor_role="user",
            canonical_payload_json=canonical_payload,
            tenant_id=tenant_id,
        )
