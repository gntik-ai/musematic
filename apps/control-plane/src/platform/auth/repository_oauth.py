from __future__ import annotations

from datetime import UTC, datetime
from platform.auth.models import OAuthAuditEntry, OAuthLink, OAuthProvider, UserCredential
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class OAuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_provider_by_type(self, provider_type: str) -> OAuthProvider | None:
        result = await self.session.execute(
            select(OAuthProvider).where(OAuthProvider.provider_type == provider_type)
        )
        return result.scalar_one_or_none()

    async def get_all_providers(self) -> list[OAuthProvider]:
        result = await self.session.execute(
            select(OAuthProvider).order_by(OAuthProvider.provider_type.asc())
        )
        return list(result.scalars().all())

    async def upsert_provider(
        self,
        provider_type: str,
        *,
        display_name: str,
        enabled: bool,
        client_id: str,
        client_secret_ref: str,
        redirect_uri: str,
        scopes: list[str],
        domain_restrictions: list[str],
        org_restrictions: list[str],
        group_role_mapping: dict[str, str],
        default_role: str,
        require_mfa: bool,
    ) -> tuple[OAuthProvider, bool]:
        provider = await self.get_provider_by_type(provider_type)
        created = provider is None
        if provider is None:
            provider = OAuthProvider(
                provider_type=provider_type,
                display_name=display_name,
                enabled=enabled,
                client_id=client_id,
                client_secret_ref=client_secret_ref,
                redirect_uri=redirect_uri,
                scopes=list(scopes),
                domain_restrictions=list(domain_restrictions),
                org_restrictions=list(org_restrictions),
                group_role_mapping=dict(group_role_mapping),
                default_role=default_role,
                require_mfa=require_mfa,
            )
            self.session.add(provider)
        else:
            provider.display_name = display_name
            provider.enabled = enabled
            provider.client_id = client_id
            provider.client_secret_ref = client_secret_ref
            provider.redirect_uri = redirect_uri
            provider.scopes = list(scopes)
            provider.domain_restrictions = list(domain_restrictions)
            provider.org_restrictions = list(org_restrictions)
            provider.group_role_mapping = dict(group_role_mapping)
            provider.default_role = default_role
            provider.require_mfa = require_mfa
        await self.session.flush()
        return provider, created

    async def get_link_by_external(self, provider_id: UUID, external_id: str) -> OAuthLink | None:
        result = await self.session.execute(
            select(OAuthLink)
            .options(selectinload(OAuthLink.provider))
            .where(
                OAuthLink.provider_id == provider_id,
                OAuthLink.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_link_for_user_provider(
        self,
        user_id: UUID,
        provider_id: UUID,
    ) -> OAuthLink | None:
        result = await self.session.execute(
            select(OAuthLink)
            .options(selectinload(OAuthLink.provider))
            .where(OAuthLink.user_id == user_id, OAuthLink.provider_id == provider_id)
        )
        return result.scalar_one_or_none()

    async def get_links_for_user(self, user_id: UUID) -> list[OAuthLink]:
        result = await self.session.execute(
            select(OAuthLink)
            .options(selectinload(OAuthLink.provider))
            .where(OAuthLink.user_id == user_id)
            .order_by(OAuthLink.linked_at.asc())
        )
        return list(result.scalars().all())

    async def create_link(
        self,
        *,
        user_id: UUID,
        provider_id: UUID,
        external_id: str,
        external_email: str | None,
        external_name: str | None,
        external_avatar_url: str | None,
        external_groups: list[str],
        last_login_at: datetime | None = None,
    ) -> OAuthLink:
        link = OAuthLink(
            user_id=user_id,
            provider_id=provider_id,
            external_id=external_id,
            external_email=external_email,
            external_name=external_name,
            external_avatar_url=external_avatar_url,
            external_groups=list(external_groups),
            last_login_at=last_login_at,
        )
        self.session.add(link)
        await self.session.flush()
        return link

    async def update_link(
        self,
        link: OAuthLink,
        *,
        external_email: str | None,
        external_name: str | None,
        external_avatar_url: str | None,
        external_groups: list[str],
        last_login_at: datetime | None,
    ) -> OAuthLink:
        link.external_email = external_email
        link.external_name = external_name
        link.external_avatar_url = external_avatar_url
        link.external_groups = list(external_groups)
        link.last_login_at = last_login_at
        await self.session.flush()
        return link

    async def delete_link(self, link: OAuthLink) -> None:
        await self.session.delete(link)
        await self.session.flush()

    async def count_auth_methods(self, user_id: UUID) -> int:
        local_result = await self.session.execute(
            select(func.count(UserCredential.user_id)).where(
                UserCredential.user_id == user_id,
                UserCredential.deleted_at.is_(None),
            )
        )
        oauth_result = await self.session.execute(
            select(func.count(OAuthLink.id)).where(OAuthLink.user_id == user_id)
        )
        return int(local_result.scalar() or 0) + int(oauth_result.scalar() or 0)

    async def create_audit_entry(
        self,
        *,
        provider_type: str | None,
        provider_id: UUID | None,
        user_id: UUID | None,
        external_id: str | None,
        action: str,
        outcome: str,
        failure_reason: str | None,
        source_ip: str | None,
        user_agent: str | None,
        actor_id: UUID | None,
        changed_fields: dict[str, Any] | None,
    ) -> OAuthAuditEntry:
        entry = OAuthAuditEntry(
            provider_type=provider_type,
            provider_id=provider_id,
            user_id=user_id,
            external_id=external_id,
            action=action,
            outcome=outcome,
            failure_reason=failure_reason,
            source_ip=source_ip,
            user_agent=user_agent,
            actor_id=actor_id,
            changed_fields=changed_fields,
            created_at=datetime.now(UTC),
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_audit_entries(
        self,
        *,
        provider_type: str | None = None,
        user_id: UUID | None = None,
        outcome: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[OAuthAuditEntry]:
        query = select(OAuthAuditEntry).order_by(OAuthAuditEntry.created_at.desc())
        if provider_type is not None:
            query = query.where(OAuthAuditEntry.provider_type == provider_type)
        if user_id is not None:
            query = query.where(OAuthAuditEntry.user_id == user_id)
        if outcome is not None:
            query = query.where(OAuthAuditEntry.outcome == outcome)
        if start_time is not None:
            query = query.where(OAuthAuditEntry.created_at >= start_time)
        if end_time is not None:
            query = query.where(OAuthAuditEntry.created_at <= end_time)
        result = await self.session.execute(query.limit(limit))
        return list(result.scalars().all())
