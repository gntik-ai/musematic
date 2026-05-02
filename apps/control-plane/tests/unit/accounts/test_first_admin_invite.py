from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from platform.accounts.exceptions import SetupTokenInvalidError
from platform.accounts.first_admin_invite import TenantFirstAdminInviteService
from platform.accounts.models import TenantFirstAdminInvitation
from platform.common.config import PlatformSettings
from platform.tenants.models import Tenant
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from tests.auth_support import RecordingProducer


class _ScalarResult:
    def __init__(self, value: object | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object | None:
        return self.value


class _Session:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flushed = 0
        self.invitation: TenantFirstAdminInvitation | None = None
        self.tenant = SimpleNamespace(id=uuid4(), slug="acme", display_name="Acme")

    def add(self, instance: object) -> None:
        if getattr(instance, "id", None) is None:
            instance.id = uuid4()
        if getattr(instance, "created_at", None) is None:
            instance.created_at = datetime.now(UTC)
        self.added.append(instance)
        if isinstance(instance, TenantFirstAdminInvitation):
            self.invitation = instance

    async def flush(self) -> None:
        self.flushed += 1
        for instance in self.added:
            if getattr(instance, "id", None) is None:
                instance.id = uuid4()
            if getattr(instance, "created_at", None) is None:
                instance.created_at = datetime.now(UTC)

    async def execute(self, _statement: object) -> _ScalarResult:
        return _ScalarResult(self.invitation)

    async def get(self, model: type[object], _id: UUID) -> object | None:
        if model is Tenant:
            return self.tenant
        if model is TenantFirstAdminInvitation:
            return self.invitation
        return None


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, object]] = []

    async def append(self, *_args: object, **kwargs: object) -> None:
        self.entries.append(kwargs)


class _Notifications:
    def __init__(self) -> None:
        self.invites: list[tuple[str, str, str | None]] = []

    async def send_invitation_email(
        self,
        invitation_id: UUID,
        email: str,
        token: str,
        inviter_id: UUID,
        message: str | None,
    ) -> None:
        del invitation_id, inviter_id
        self.invites.append((email, token, message))


def _service() -> tuple[
    TenantFirstAdminInviteService,
    _Session,
    RecordingProducer,
    _Audit,
    _Notifications,
]:
    session = _Session()
    producer = RecordingProducer()
    audit = _Audit()
    notifications = _Notifications()
    return (
        TenantFirstAdminInviteService(
            session=session,  # type: ignore[arg-type]
            settings=PlatformSettings(),
            producer=producer,
            audit_chain=audit,  # type: ignore[arg-type]
            notification_client=notifications,
        ),
        session,
        producer,
        audit,
        notifications,
    )


def _invitation(
    *,
    tenant_id: UUID | None = None,
    setup_step_state: dict[str, object] | None = None,
) -> TenantFirstAdminInvitation:
    return TenantFirstAdminInvitation(
        id=uuid4(),
        tenant_id=tenant_id or uuid4(),
        token_hash=TenantFirstAdminInviteService.hash_token("setup-token"),
        target_email="admin@example.com",
        expires_at=datetime.now(UTC) + timedelta(days=1),
        created_by_super_admin_id=uuid4(),
        created_at=datetime.now(UTC) - timedelta(minutes=5),
        setup_step_state=setup_step_state or {},
        mfa_required=True,
    )

def test_first_admin_invite_lifecycle_contract_is_present() -> None:
    source = Path("src/platform/accounts/first_admin_invite.py").read_text(encoding="utf-8")

    for method in ("issue", "validate", "consume", "resend", "resend_for_tenant"):
        assert f"async def {method}" in source
    assert "prior_token_invalidated_at" in source
    assert "send_invitation_email" in source
    assert "accounts_first_admin_invitation_issued_total" in source
    assert "accounts_first_admin_invitation_resent_total" in source
    assert "accounts_first_admin_invitation_consumed_seconds" in source


@pytest.mark.asyncio
async def test_issue_validate_record_consume_and_resend_paths() -> None:
    service, session, producer, audit, notifications = _service()
    tenant_id = session.tenant.id
    super_admin_id = uuid4()

    invitation, token = await service.issue(tenant_id, "Admin@Example.COM", super_admin_id)

    assert invitation.target_email == "admin@example.com"
    assert notifications.invites[0][0] == "admin@example.com"
    assert notifications.invites[0][2] == "Complete Enterprise tenant setup."
    assert producer.events[-1]["event_type"] == "accounts.first_admin_invitation.issued"
    assert audit.entries[-1]["event_type"] == "accounts.first_admin_invitation.issued"

    invitation.setup_step_state = {"tos": True, "credentials": True}
    validated = await service.validate(token)
    assert validated.current_step == "mfa"
    assert validated.completed_steps == ["credentials", "tos"]

    await service.record_step(
        token,
        "workspace",
        {"workspace_id": str(uuid4()), "name": "Launch"},
        user_id=uuid4(),
    )
    await service.record_step(token, "invitations", {"invitations_sent": 2}, user_id=uuid4())
    invitation.setup_step_state["credentials"] = True
    invitation.setup_step_state["mfa"] = True
    consumed = await service.consume(token, uuid4())
    assert consumed.consumed_at is not None
    assert producer.events[-1]["event_type"] == "accounts.setup.completed"

    fresh, fresh_token = await service.resend(invitation.id, super_admin_id)
    assert invitation.prior_token_invalidated_at is not None
    assert fresh.id != invitation.id
    assert fresh_token
    assert producer.events[-1]["event_type"] == "accounts.first_admin_invitation.resent"


@pytest.mark.asyncio
async def test_token_lookup_rejects_invalid_and_current_step_handles_all_done() -> None:
    service, session, _producer, _audit, _notifications = _service()
    assert service.current_step(_invitation(setup_step_state={"tos": True})) == "credentials"
    assert (
        service.current_step(
            _invitation(
                setup_step_state={
                    "tos": True,
                    "credentials": True,
                    "mfa": True,
                    "workspace": True,
                    "invitations": True,
                }
            )
        )
        == "done"
    )

    session.invitation = None
    with pytest.raises(SetupTokenInvalidError):
        await service.validate("missing")

    invitation = _invitation(setup_step_state={})
    session.invitation = invitation
    invitation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(SetupTokenInvalidError):
        await service.validate("setup-token")
    invitation.expires_at = datetime.now(UTC) + timedelta(days=1)
    invitation.consumed_at = datetime.now(UTC)
    with pytest.raises(SetupTokenInvalidError):
        await service.validate("setup-token")
    invitation.consumed_at = None
    invitation.prior_token_invalidated_at = datetime.now(UTC)
    with pytest.raises(SetupTokenInvalidError):
        await service.validate("setup-token")
