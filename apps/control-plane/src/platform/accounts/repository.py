from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.accounts.models import (
    ApprovalRequest,
    EmailVerification,
    Invitation,
    InvitationStatus,
    SignupSource,
    User,
    UserStatus,
)
from platform.accounts.schemas import PendingApprovalItem
from platform.common.clients.redis import AsyncRedisClient
from platform.common.models.user import User as PlatformUser
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class AccountsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_user(
        self,
        email: str,
        display_name: str,
        status: UserStatus,
        signup_source: SignupSource,
        invitation_id: UUID | None = None,
    ) -> User:
        user_id = uuid4()
        account_user = User(
            id=user_id,
            email=email.lower(),
            display_name=display_name,
            status=status,
            signup_source=signup_source,
            invitation_id=invitation_id,
        )
        platform_user = PlatformUser(
            id=user_id,
            email=email.lower(),
            display_name=display_name,
            status=status.value,
        )
        self.session.add(account_user)
        self.session.add(platform_user)
        await self.session.flush()
        return account_user

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_user_workspace_limit(self, user_id: UUID) -> int | None:
        user = await self.get_user_by_id(user_id)
        if user is None:
            return None
        return int(getattr(user, "max_workspaces", 0))

    async def get_user_for_update(self, user_id: UUID) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def update_user_status(
        self,
        user_id: UUID,
        new_status: UserStatus,
        **kwargs: object,
    ) -> User:
        user = await self.get_user_for_update(user_id)
        if user is None:
            raise ValueError("User not found")
        user.status = new_status
        for key, value in kwargs.items():
            setattr(user, key, value)

        platform_result = await self.session.execute(
            select(PlatformUser).where(PlatformUser.id == user_id).with_for_update()
        )
        platform_user = platform_result.scalar_one_or_none()
        if platform_user is not None:
            platform_user.status = new_status.value
            if "deleted_at" in kwargs:
                platform_user.deleted_at = kwargs.get("deleted_at")  # type: ignore[assignment]
        await self.session.flush()
        return user

    async def create_email_verification(
        self,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> EmailVerification:
        verification = EmailVerification(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            consumed=False,
        )
        self.session.add(verification)
        await self.session.flush()
        return verification

    async def get_active_verification_by_token_hash(
        self,
        token_hash: str,
    ) -> EmailVerification | None:
        result = await self.session.execute(
            select(EmailVerification).where(
                EmailVerification.token_hash == token_hash,
                EmailVerification.consumed.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def consume_verification(self, verification_id: UUID) -> None:
        verification = await self.session.get(EmailVerification, verification_id)
        if verification is not None:
            verification.consumed = True
            await self.session.flush()

    async def get_resend_count(
        self,
        redis_client: AsyncRedisClient,
        user_id: UUID,
    ) -> int:
        client = await redis_client._get_client()
        raw = await client.get(f"resend_verify:{user_id}")
        return int(raw or 0)

    async def increment_resend_count(
        self,
        redis_client: AsyncRedisClient,
        user_id: UUID,
    ) -> int:
        client = await redis_client._get_client()
        key = f"resend_verify:{user_id}"
        count = int(await client.incr(key))
        if count == 1:
            await client.expire(key, 3600)
        return count

    async def create_approval_request(
        self,
        user_id: UUID,
        requested_at: datetime,
    ) -> ApprovalRequest:
        approval_request = ApprovalRequest(user_id=user_id, requested_at=requested_at)
        self.session.add(approval_request)
        await self.session.flush()
        return approval_request

    async def get_approval_request_for_update(self, user_id: UUID) -> ApprovalRequest | None:
        result = await self.session.execute(
            select(ApprovalRequest).where(ApprovalRequest.user_id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_pending_approvals(
        self,
        page: int,
        page_size: int,
    ) -> tuple[list[PendingApprovalItem], int]:
        total = await self.session.scalar(
            select(func.count())
            .select_from(ApprovalRequest)
            .join(User, User.id == ApprovalRequest.user_id)
            .where(User.status == UserStatus.pending_approval)
        )
        result = await self.session.execute(
            select(User, ApprovalRequest)
            .join(ApprovalRequest, ApprovalRequest.user_id == User.id)
            .where(User.status == UserStatus.pending_approval)
            .order_by(ApprovalRequest.requested_at.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = [
            PendingApprovalItem(
                user_id=user.id,
                email=user.email,
                display_name=user.display_name,
                registered_at=user.created_at,
                email_verified_at=user.email_verified_at or approval.requested_at,
            )
            for user, approval in result.all()
        ]
        return items, int(total or 0)

    async def create_invitation(
        self,
        inviter_id: UUID,
        invitee_email: str,
        token_hash: str,
        roles_json: str,
        workspace_ids_json: str | None,
        message: str | None,
        expires_at: datetime,
    ) -> Invitation:
        invitation = Invitation(
            inviter_id=inviter_id,
            invitee_email=invitee_email.lower(),
            token_hash=token_hash,
            roles_json=roles_json,
            workspace_ids_json=workspace_ids_json,
            invitee_message=message,
            expires_at=expires_at,
            status=InvitationStatus.pending,
        )
        self.session.add(invitation)
        await self.session.flush()
        return invitation

    async def get_invitation_by_token_hash(self, token_hash: str) -> Invitation | None:
        result = await self.session.execute(
            select(Invitation).where(Invitation.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def consume_invitation(self, invitation_id: UUID, user_id: UUID) -> None:
        invitation = await self.session.get(Invitation, invitation_id)
        if invitation is not None:
            invitation.status = InvitationStatus.consumed
            invitation.consumed_by_user_id = user_id
            invitation.consumed_at = datetime.now(UTC)
            await self.session.flush()

    async def revoke_invitation(self, invitation_id: UUID, revoked_by: UUID) -> None:
        invitation = await self.session.get(Invitation, invitation_id)
        if invitation is not None:
            invitation.status = InvitationStatus.revoked
            invitation.revoked_by = revoked_by
            invitation.revoked_at = datetime.now(UTC)
            await self.session.flush()

    async def list_invitations_by_inviter(
        self,
        inviter_id: UUID,
        status_filter: InvitationStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Invitation], int]:
        base_query = select(Invitation).where(Invitation.inviter_id == inviter_id)
        count_query = (
            select(func.count()).select_from(Invitation).where(Invitation.inviter_id == inviter_id)
        )
        if status_filter is not None:
            base_query = base_query.where(Invitation.status == status_filter)
            count_query = count_query.where(Invitation.status == status_filter)
        total = await self.session.scalar(count_query)
        result = await self.session.execute(
            base_query.order_by(Invitation.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def get_invitation_by_id(self, invitation_id: UUID) -> Invitation | None:
        return await self.session.get(Invitation, invitation_id)

    @staticmethod
    def deserialize_roles(invitation: Invitation) -> list[str]:
        return [str(item) for item in json.loads(invitation.roles_json)]

    @staticmethod
    def deserialize_workspace_ids(invitation: Invitation) -> list[UUID] | None:
        if not invitation.workspace_ids_json:
            return None
        return [UUID(str(item)) for item in json.loads(invitation.workspace_ids_json)]
