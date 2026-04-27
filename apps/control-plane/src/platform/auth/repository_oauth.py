from __future__ import annotations

from datetime import UTC, datetime
from platform.audit.service import AuditChainService
from platform.auth.models import (
    OAuthAuditEntry,
    OAuthLink,
    OAuthProvider,
    OAuthProviderRateLimit,
    OAuthProviderSource,
    UserCredential,
)
from platform.common.audit_hook import audit_chain_hook
from typing import Any
from uuid import UUID

from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class OAuthRepository:
    def __init__(self, session: AsyncSession, audit_chain: AuditChainService | None = None) -> None:
        self.session = session
        self.audit_chain = audit_chain

    async def get_provider_by_type(self, provider_type: str) -> OAuthProvider | None:
        result = await self.session.execute(
            select(OAuthProvider).where(OAuthProvider.provider_type == provider_type)
        )
        return result.scalar_one_or_none()

    async def get_by_type_for_update(self, provider_type: str) -> OAuthProvider | None:
        result = await self.session.execute(
            select(OAuthProvider)
            .where(OAuthProvider.provider_type == provider_type)
            .with_for_update(skip_locked=True)
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
        source: str | OAuthProviderSource = OAuthProviderSource.manual,
        last_edited_by: UUID | None = None,
        last_edited_at: datetime | None = None,
        last_successful_auth_at: datetime | None = None,
    ) -> tuple[OAuthProvider, bool]:
        values = {
            "provider_type": provider_type,
            "display_name": display_name,
            "enabled": enabled,
            "client_id": client_id,
            "client_secret_ref": client_secret_ref,
            "redirect_uri": redirect_uri,
            "scopes": list(scopes),
            "domain_restrictions": list(domain_restrictions),
            "org_restrictions": list(org_restrictions),
            "group_role_mapping": dict(group_role_mapping),
            "default_role": default_role,
            "require_mfa": require_mfa,
            "source": str(source),
            "last_edited_by": last_edited_by,
            "last_edited_at": last_edited_at,
        }
        if last_successful_auth_at is not None:
            values["last_successful_auth_at"] = last_successful_auth_at
        created_expr: Any = literal_column("xmax = 0").label("created")
        statement = (
            insert(OAuthProvider)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[OAuthProvider.provider_type],
                set_={key: value for key, value in values.items() if key != "provider_type"},
            )
            .returning(OAuthProvider.id, created_expr)
        )
        row = (await self.session.execute(statement)).one()
        provider = await self.session.get(OAuthProvider, row.id, populate_existing=True)
        if provider is None:  # pragma: no cover - guarded by RETURNING
            raise LookupError(f"OAuth provider {provider_type} disappeared after upsert")
        return provider, bool(row.created)

    async def update_provider_last_successful_auth(
        self,
        provider: OAuthProvider,
        timestamp: datetime,
    ) -> None:
        provider.last_successful_auth_at = timestamp
        await self.session.flush()

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
        inserted_link_id = (
            await self.session.execute(
                insert(OAuthLink)
                .values(
                    user_id=user_id,
                    provider_id=provider_id,
                    external_id=external_id,
                    external_email=external_email,
                    external_name=external_name,
                    external_avatar_url=external_avatar_url,
                    external_groups=list(external_groups),
                    last_login_at=last_login_at,
                )
                .on_conflict_do_nothing(
                    index_elements=[OAuthLink.provider_id, OAuthLink.external_id]
                )
                .returning(OAuthLink.id)
            )
        ).scalar_one_or_none()

        if inserted_link_id is None:
            existing = await self.get_link_by_external(provider_id, external_id)
            if existing is None:  # pragma: no cover - guarded by unique link constraint
                raise LookupError(
                    f"OAuth link for provider={provider_id} external_id={external_id} "
                    "disappeared after concurrent create"
                )
            if existing.user_id != user_id:
                raise ValueError("OAuth link already belongs to a different user")
            existing.external_email = external_email
            existing.external_name = external_name
            existing.external_avatar_url = external_avatar_url
            existing.external_groups = list(external_groups)
            existing.last_login_at = last_login_at
            await self.session.flush()
            return existing

        link = await self.session.get(OAuthLink, inserted_link_id, populate_existing=True)
        if link is None:  # pragma: no cover - guarded by RETURNING
            raise LookupError(
                f"OAuth link for provider={provider_id} external_id={external_id} "
                "disappeared after insert"
            )
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

    async def count_active_links(self, provider_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count(func.distinct(OAuthLink.user_id))).where(
                OAuthLink.provider_id == provider_id
            )
        )
        return int(result.scalar() or 0)

    async def count_successful_auths_since(
        self,
        provider_id: UUID,
        since: datetime,
    ) -> int:
        result = await self.session.execute(
            select(func.count(OAuthAuditEntry.id)).where(
                OAuthAuditEntry.provider_id == provider_id,
                OAuthAuditEntry.action == "sign_in_succeeded",
                OAuthAuditEntry.outcome == "success",
                OAuthAuditEntry.created_at >= since,
            )
        )
        return int(result.scalar() or 0)

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
        if self.audit_chain is not None:
            await audit_chain_hook(
                self.audit_chain,
                entry.id,
                "auth",
                {
                    "provider_type": entry.provider_type,
                    "provider_id": entry.provider_id,
                    "user_id": entry.user_id,
                    "external_id": entry.external_id,
                    "action": entry.action,
                    "outcome": entry.outcome,
                    "failure_reason": entry.failure_reason,
                    "source_ip": entry.source_ip,
                    "actor_id": entry.actor_id,
                    "changed_fields": entry.changed_fields,
                    "created_at": entry.created_at,
                },
            )
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

    async def get_history(
        self,
        provider_id: UUID,
        *,
        limit: int = 100,
        cursor: datetime | None = None,
    ) -> list[OAuthAuditEntry]:
        query = (
            select(OAuthAuditEntry)
            .where(OAuthAuditEntry.provider_id == provider_id)
            .order_by(OAuthAuditEntry.created_at.desc(), OAuthAuditEntry.id.desc())
        )
        if cursor is not None:
            query = query.where(OAuthAuditEntry.created_at < cursor)
        result = await self.session.execute(query.limit(limit))
        return list(result.scalars().all())

    async def get_rate_limits(self, provider_id: UUID) -> OAuthProviderRateLimit | None:
        result = await self.session.execute(
            select(OAuthProviderRateLimit).where(OAuthProviderRateLimit.provider_id == provider_id)
        )
        return result.scalar_one_or_none()

    async def upsert_rate_limits(
        self,
        provider_id: UUID,
        *,
        per_ip_max: int,
        per_ip_window: int,
        per_user_max: int,
        per_user_window: int,
        global_max: int,
        global_window: int,
    ) -> OAuthProviderRateLimit:
        values = {
            "provider_id": provider_id,
            "per_ip_max": per_ip_max,
            "per_ip_window": per_ip_window,
            "per_user_max": per_user_max,
            "per_user_window": per_user_window,
            "global_max": global_max,
            "global_window": global_window,
        }
        row_id = (
            await self.session.execute(
                insert(OAuthProviderRateLimit)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[OAuthProviderRateLimit.provider_id],
                    set_={key: value for key, value in values.items() if key != "provider_id"},
                )
                .returning(OAuthProviderRateLimit.id)
            )
        ).scalar_one()
        limits = await self.session.get(
            OAuthProviderRateLimit,
            row_id,
            populate_existing=True,
        )
        if limits is None:  # pragma: no cover - guarded by RETURNING
            raise LookupError(f"OAuth rate limits for provider={provider_id} disappeared")
        return limits
