from __future__ import annotations

from datetime import UTC, datetime
from platform.auth.models import (
    AuthAttempt,
    MfaEnrollment,
    PasswordResetToken,
    RolePermission,
    ServiceAccountCredential,
    UserCredential,
    UserRole,
)
from platform.common.models.user import User as PlatformUser
import hashlib
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession


class AuthRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_credential_by_email(self, email: str) -> UserCredential | None:
        result = await self.db.execute(
            select(UserCredential).where(UserCredential.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_platform_user(self, user_id: UUID) -> PlatformUser | None:
        result = await self.db.execute(select(PlatformUser).where(PlatformUser.id == user_id))
        return result.scalar_one_or_none()

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

    async def get_role_permissions(self, role: str) -> list[RolePermission]:
        result = await self.db.execute(
            select(RolePermission).where(RolePermission.role == role)
        )
        return list(result.scalars().all())

    async def get_all_role_permissions(self) -> list[RolePermission]:
        result = await self.db.execute(select(RolePermission))
        return list(result.scalars().all())

    async def assign_user_role(
        self,
        user_id: UUID,
        role: str,
        workspace_id: UUID | None,
    ) -> UserRole:
        assignment = UserRole(user_id=user_id, role=role, workspace_id=workspace_id)
        self.db.add(assignment)
        await self.db.flush()
        return assignment

    async def revoke_user_role(self, user_role_id: UUID) -> None:
        await self.db.execute(delete(UserRole).where(UserRole.id == user_role_id))

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
        return bool(result.rowcount)

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
            select(ServiceAccountCredential).where(
                ServiceAccountCredential.status == "active"
            )
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
