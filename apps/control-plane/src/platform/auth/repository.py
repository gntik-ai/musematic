from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime
from platform.accounts.models import SignupSource
from platform.accounts.models import User as AccountUser
from platform.accounts.models import UserStatus as AccountUserStatus
from platform.auth.models import (
    AuthAttempt,
    IBORConnector,
    IBORSyncRun,
    MfaEnrollment,
    PasswordResetToken,
    RolePermission,
    ServiceAccountCredential,
    UserCredential,
    UserRole,
)
from platform.common.models.user import User as PlatformUser
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession


class AuthRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_account_user(self, user_id: UUID) -> AccountUser | None:
        result = await self.db.execute(select(AccountUser).where(AccountUser.id == user_id))
        return result.scalar_one_or_none()

    async def get_account_user_by_email(self, email: str) -> AccountUser | None:
        result = await self.db.execute(
            select(AccountUser).where(AccountUser.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def ensure_account_user(
        self,
        user_id: UUID,
        email: str,
        display_name: str,
    ) -> AccountUser:
        normalized_email = email.lower()
        now = datetime.now(UTC)
        await self.db.execute(
            insert(AccountUser)
            .values(
                id=user_id,
                email=normalized_email,
                display_name=display_name,
                status=AccountUserStatus.active,
                signup_source=SignupSource.self_registration,
                email_verified_at=now,
                activated_at=now,
                max_workspaces=0,
            )
            .on_conflict_do_nothing()
        )
        account_user = await self.get_account_user(user_id)
        if account_user is not None:
            return account_user
        existing = await self.get_account_user_by_email(normalized_email)
        if existing is not None and existing.id == user_id:
            return existing
        if existing is not None:
            raise ValueError('Account email already belongs to a different user')
        raise LookupError(f'Account user for {user_id} disappeared after ensure')

    async def get_credential_by_email(self, email: str) -> UserCredential | None:
        result = await self.db.execute(
            select(UserCredential).where(UserCredential.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_platform_user(self, user_id: UUID) -> PlatformUser | None:
        result = await self.db.execute(select(PlatformUser).where(PlatformUser.id == user_id))
        return result.scalar_one_or_none()

    async def get_platform_user_by_email(self, email: str) -> PlatformUser | None:
        result = await self.db.execute(
            select(PlatformUser).where(PlatformUser.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def create_platform_user(
        self,
        user_id: UUID,
        email: str,
        display_name: str,
    ) -> PlatformUser:
        platform_user = PlatformUser(
            id=user_id,
            email=email.lower(),
            display_name=display_name,
            status="active",
        )
        self.db.add(platform_user)
        await self.db.flush()
        return platform_user

    async def create_credential(
        self,
        user_id: UUID,
        email: str,
        password_hash: str,
    ) -> UserCredential:
        credential = UserCredential(
            user_id=user_id,
            email=email.lower(),
            password_hash=password_hash,
            is_active=True,
        )
        self.db.add(credential)
        await self.db.flush()
        return credential

    async def get_credential_by_user_id(self, user_id: UUID) -> UserCredential | None:
        result = await self.db.execute(
            select(UserCredential).where(UserCredential.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def ensure_credential(
        self,
        user_id: UUID,
        email: str,
        password_hash: str,
    ) -> UserCredential:
        normalized_email = email.lower()
        await self.db.execute(
            insert(UserCredential)
            .values(
                user_id=user_id,
                email=normalized_email,
                password_hash=password_hash,
                is_active=True,
            )
            .on_conflict_do_nothing()
        )
        credential = await self.get_credential_by_user_id(user_id)
        if credential is not None:
            return credential
        existing = await self.get_credential_by_email(normalized_email)
        if existing is not None and existing.user_id == user_id:
            return existing
        if existing is not None:
            raise ValueError('Credential email already belongs to a different user')
        raise LookupError(f'Credential for user {user_id} disappeared after ensure')

    async def create_password_reset_token(
        self,
        user_id: UUID,
        raw_token: str,
        expires_at: datetime,
    ) -> PasswordResetToken:
        token = PasswordResetToken(
            user_id=user_id,
            token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
            expires_at=expires_at,
        )
        self.db.add(token)
        await self.db.flush()
        return token

    async def update_password_hash(self, user_id: UUID, new_hash: str) -> None:
        await self.db.execute(
            update(UserCredential)
            .where(UserCredential.user_id == user_id)
            .values(password_hash=new_hash)
        )

    async def get_user_roles(
        self,
        user_id: UUID,
        workspace_id: UUID | None,
    ) -> list[UserRole]:
        query = select(UserRole).where(UserRole.user_id == user_id)
        if workspace_id is not None:
            query = query.where(
                (UserRole.workspace_id == workspace_id) | (UserRole.workspace_id.is_(None))
            )
        result = await self.db.execute(query.order_by(UserRole.created_at.asc()))
        return list(result.scalars().all())

    async def list_user_roles(
        self,
        *,
        user_id: UUID | None = None,
        user_email: str | None = None,
    ) -> list[UserRole]:
        query = select(UserRole)
        if user_id is not None:
            query = query.where(UserRole.user_id == user_id)
        elif user_email is not None:
            user = await self.get_platform_user_by_email(user_email)
            if user is None:
                return []
            query = query.where(UserRole.user_id == user.id)
        else:
            raise ValueError("user_id or user_email is required")
        result = await self.db.execute(query.order_by(UserRole.created_at.asc()))
        return list(result.scalars().all())

    async def get_user_roles_by_source_connector(
        self,
        user_id: UUID,
        source_connector_id: UUID,
    ) -> list[UserRole]:
        result = await self.db.execute(
            select(UserRole)
            .where(
                UserRole.user_id == user_id,
                UserRole.source_connector_id == source_connector_id,
            )
            .order_by(UserRole.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_role_permissions(self, role: str) -> list[RolePermission]:
        result = await self.db.execute(select(RolePermission).where(RolePermission.role == role))
        return list(result.scalars().all())

    async def get_all_role_permissions(self) -> list[RolePermission]:
        result = await self.db.execute(select(RolePermission))
        return list(result.scalars().all())

    async def assign_user_role(
        self,
        user_id: UUID,
        role: str,
        workspace_id: UUID | None,
        source_connector_id: UUID | None = None,
    ) -> UserRole:
        workspace_clause = (
            UserRole.workspace_id.is_(None)
            if workspace_id is None
            else UserRole.workspace_id == workspace_id
        )
        existing = await self.db.execute(
            select(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.role == role,
                workspace_clause,
            )
        )
        assignment = existing.scalar_one_or_none()
        if assignment is not None:
            if assignment.source_connector_id is None:
                return assignment
            if source_connector_id is None:
                assignment.source_connector_id = None
            elif assignment.source_connector_id != source_connector_id:
                assignment.source_connector_id = source_connector_id
            await self.db.flush()
            return assignment

        assignment = UserRole(
            user_id=user_id,
            role=role,
            workspace_id=workspace_id,
            source_connector_id=source_connector_id,
        )
        self.db.add(assignment)
        await self.db.flush()
        return assignment

    async def revoke_user_role(self, user_role_id: UUID) -> None:
        await self.db.execute(delete(UserRole).where(UserRole.id == user_role_id))

    async def list_user_roles_by_connector(self, connector_id: UUID) -> list[UserRole]:
        result = await self.db.execute(
            select(UserRole)
            .where(UserRole.source_connector_id == connector_id)
            .order_by(UserRole.created_at.asc())
        )
        return list(result.scalars().all())

    async def record_auth_attempt(
        self,
        user_id: UUID | None,
        email: str,
        ip: str,
        user_agent: str,
        outcome: str,
    ) -> None:
        attempt = AuthAttempt(
            user_id=user_id,
            email=email.lower(),
            ip_address=ip,
            user_agent=user_agent,
            outcome=outcome,
        )
        self.db.add(attempt)
        await self.db.flush()

    async def get_mfa_enrollment(self, user_id: UUID) -> MfaEnrollment | None:
        result = await self.db.execute(
            select(MfaEnrollment)
            .where(MfaEnrollment.user_id == user_id)
            .order_by(MfaEnrollment.created_at.desc())
        )
        return result.scalars().first()

    async def create_mfa_enrollment(
        self,
        user_id: UUID,
        encrypted_secret: str,
        recovery_hashes: list[str],
        expires_at: datetime,
    ) -> MfaEnrollment:
        enrollment = MfaEnrollment(
            user_id=user_id,
            encrypted_secret=encrypted_secret,
            recovery_codes_hash=recovery_hashes,
            expires_at=expires_at,
        )
        self.db.add(enrollment)
        await self.db.flush()
        return enrollment

    async def activate_mfa_enrollment(self, enrollment_id: UUID) -> None:
        await self.db.execute(
            update(MfaEnrollment)
            .where(MfaEnrollment.id == enrollment_id)
            .values(
                status="active",
                enrolled_at=datetime.now(UTC),
                expires_at=None,
            )
        )

    async def disable_mfa_enrollment(self, user_id: UUID) -> bool:
        result = await self.db.execute(
            update(MfaEnrollment)
            .where(MfaEnrollment.user_id == user_id)
            .values(status="disabled", expires_at=None)
        )
        return bool(getattr(result, "rowcount", 0))

    async def consume_recovery_code(
        self,
        enrollment_id: UUID,
        code_index: int,
        updated_hashes: list[str],
    ) -> None:
        del code_index
        await self.db.execute(
            update(MfaEnrollment)
            .where(MfaEnrollment.id == enrollment_id)
            .values(recovery_codes_hash=updated_hashes)
        )

    async def get_active_service_accounts(self) -> list[ServiceAccountCredential]:
        result = await self.db.execute(
            select(ServiceAccountCredential).where(ServiceAccountCredential.status == "active")
        )
        return list(result.scalars().all())

    async def create_service_account_credential(
        self,
        sa_id: UUID,
        name: str,
        key_hash: str,
        role: str,
        workspace_id: UUID | None,
    ) -> ServiceAccountCredential:
        credential = ServiceAccountCredential(
            service_account_id=sa_id,
            name=name,
            api_key_hash=key_hash,
            role=role,
            status="active",
            workspace_id=workspace_id,
        )
        self.db.add(credential)
        await self.db.flush()
        return credential

    async def update_service_account_key_hash(
        self,
        sa_id: UUID,
        new_hash: str,
        status: str,
    ) -> None:
        await self.db.execute(
            update(ServiceAccountCredential)
            .where(ServiceAccountCredential.service_account_id == sa_id)
            .values(api_key_hash=new_hash, status=status)
        )

    async def get_service_account_by_id(self, sa_id: UUID) -> ServiceAccountCredential | None:
        result = await self.db.execute(
            select(ServiceAccountCredential).where(
                ServiceAccountCredential.service_account_id == sa_id
            )
        )
        return result.scalar_one_or_none()

    async def revoke_service_account(self, sa_id: UUID) -> None:
        await self.db.execute(
            update(ServiceAccountCredential)
            .where(ServiceAccountCredential.service_account_id == sa_id)
            .values(status="revoked")
        )

    async def get_connector_by_name(self, name: str) -> IBORConnector | None:
        result = await self.db.execute(select(IBORConnector).where(IBORConnector.name == name))
        return result.scalar_one_or_none()

    async def create_connector(
        self,
        *,
        name: str,
        source_type: Any,
        sync_mode: Any,
        cadence_seconds: int,
        credential_ref: str,
        role_mapping_policy: list[dict[str, Any]],
        enabled: bool,
        created_by: UUID,
    ) -> IBORConnector:
        connector = IBORConnector(
            name=name,
            source_type=source_type,
            sync_mode=sync_mode,
            cadence_seconds=cadence_seconds,
            credential_ref=credential_ref,
            role_mapping_policy=role_mapping_policy,
            enabled=enabled,
            created_by=created_by,
        )
        self.db.add(connector)
        await self.db.flush()
        return connector

    async def list_connectors(self) -> list[IBORConnector]:
        result = await self.db.execute(
            select(IBORConnector).order_by(IBORConnector.name.asc(), IBORConnector.id.asc())
        )
        return list(result.scalars().all())

    async def list_enabled_connectors(self) -> list[IBORConnector]:
        result = await self.db.execute(
            select(IBORConnector)
            .where(IBORConnector.enabled.is_(True))
            .order_by(IBORConnector.name.asc(), IBORConnector.id.asc())
        )
        return list(result.scalars().all())

    async def get_connector(self, connector_id: UUID) -> IBORConnector | None:
        result = await self.db.execute(
            select(IBORConnector).where(IBORConnector.id == connector_id)
        )
        return result.scalar_one_or_none()

    async def update_connector(self, connector: IBORConnector, **fields: Any) -> IBORConnector:
        for key, value in fields.items():
            setattr(connector, key, value)
        await self.db.flush()
        return connector

    async def soft_delete_connector(self, connector: IBORConnector) -> IBORConnector:
        connector.enabled = False
        await self.db.flush()
        return connector

    async def create_sync_run(
        self,
        *,
        connector_id: UUID,
        mode: Any,
        status: Any,
        counts: dict[str, int] | None = None,
        error_details: list[dict[str, Any]] | None = None,
        triggered_by: UUID | None,
    ) -> IBORSyncRun:
        run = IBORSyncRun(
            connector_id=connector_id,
            mode=mode,
            status=status,
            counts=counts or {},
            error_details=error_details or [],
            triggered_by=triggered_by,
        )
        self.db.add(run)
        await self.db.flush()
        return run

    async def get_sync_run(self, run_id: UUID) -> IBORSyncRun | None:
        result = await self.db.execute(select(IBORSyncRun).where(IBORSyncRun.id == run_id))
        return result.scalar_one_or_none()

    async def get_running_sync_run(self, connector_id: UUID) -> IBORSyncRun | None:
        result = await self.db.execute(
            select(IBORSyncRun)
            .where(
                IBORSyncRun.connector_id == connector_id,
                IBORSyncRun.status == "running",
            )
            .order_by(IBORSyncRun.started_at.desc())
        )
        return result.scalars().first()

    async def update_sync_run(
        self,
        run: IBORSyncRun,
        *,
        status: Any,
        counts: dict[str, int],
        error_details: list[dict[str, Any]],
        finished_at: datetime | None = None,
    ) -> IBORSyncRun:
        run.status = status
        run.counts = counts
        run.error_details = error_details
        run.finished_at = finished_at or datetime.now(UTC)
        await self.db.flush()
        return run

    async def touch_connector_run(
        self,
        connector: IBORConnector,
        *,
        status: str,
        last_run_at: datetime | None = None,
    ) -> None:
        connector.last_run_status = status
        connector.last_run_at = last_run_at or datetime.now(UTC)
        await self.db.flush()

    async def list_sync_runs(
        self,
        connector_id: UUID,
        *,
        limit: int,
        cursor: str | None = None,
    ) -> tuple[list[IBORSyncRun], str | None]:
        query = select(IBORSyncRun).where(IBORSyncRun.connector_id == connector_id)
        if cursor:
            started_at, run_id = self._decode_run_cursor(cursor)
            query = query.where(
                or_(
                    IBORSyncRun.started_at < started_at,
                    and_(IBORSyncRun.started_at == started_at, IBORSyncRun.id < run_id),
                )
            )
        query = query.order_by(
            IBORSyncRun.started_at.desc(),
            IBORSyncRun.id.desc(),
        ).limit(limit + 1)
        result = await self.db.execute(query)
        rows = list(result.scalars().all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            cursor_row = rows[-1]
            next_cursor = self._encode_run_cursor(cursor_row.started_at, cursor_row.id)
        return rows, next_cursor

    @staticmethod
    def _encode_run_cursor(started_at: datetime, run_id: UUID) -> str:
        raw = f"{started_at.isoformat()}|{run_id}"
        return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")

    @staticmethod
    def _decode_run_cursor(cursor: str) -> tuple[datetime, UUID]:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        started_at_raw, run_id_raw = raw.split("|", 1)
        return datetime.fromisoformat(started_at_raw), UUID(run_id_raw)
