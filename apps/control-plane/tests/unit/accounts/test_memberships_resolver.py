from __future__ import annotations

from pathlib import Path
from platform.accounts import memberships_router
from platform.accounts.memberships import MembershipsService
from platform.accounts.schemas import MembershipEntry, MembershipsListResponse
from platform.common.config import PlatformSettings
from platform.common.tenant_context import current_tenant
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest


def test_memberships_resolver_uses_platform_staff_and_email_fanout() -> None:
    source = Path("src/platform/accounts/memberships.py").read_text(encoding="utf-8")

    assert "get_platform_staff_session" in source
    assert "lower(u.email) = lower(:email)" in source
    assert "LEFT JOIN memberships" in source
    assert "tenant_display_name" in source
    assert "login_url" in source
    assert "accounts.memberships.listed" in source


class _MappingsResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def mappings(self) -> _MappingsResult:
        return self

    def __iter__(self):
        return iter(self.rows)

    def first(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None


class _MembershipSession:
    def __init__(
        self,
        rows: list[dict[str, object]],
        lookup_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.rows = rows
        self.lookup_rows = (
            lookup_rows if lookup_rows is not None else [{"email": "ADMIN@example.COM"}]
        )
        self.calls: list[dict[str, object] | None] = []

    async def execute(self, _statement: object, params: dict[str, object] | None = None) -> object:
        self.calls.append(params)
        if params and "email" in params:
            return _MappingsResult(self.rows)
        return _MappingsResult(self.lookup_rows)


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, object]] = []

    async def append(self, *_args: object, **kwargs: object) -> None:
        self.entries.append(kwargs)


@pytest.mark.asyncio
async def test_memberships_service_resolves_email_lists_memberships_and_audits() -> None:
    user_id = uuid4()
    current_tenant_id = uuid4()
    tenant_id = uuid4()
    session = _MembershipSession(
        [
            {
                "user_id": user_id,
                "tenant_id": current_tenant_id,
                "tenant_slug": "default",
                "tenant_kind": "platform",
                "tenant_display_name": "Default",
                "role": None,
            },
            {
                "user_id": uuid4(),
                "tenant_id": tenant_id,
                "tenant_slug": "acme",
                "tenant_kind": "enterprise",
                "tenant_display_name": "Acme",
                "role": "workspace_admin",
            },
        ]
    )
    audit = _Audit()
    service = MembershipsService(
        platform_staff_session=session,  # type: ignore[arg-type]
        settings=PlatformSettings(PLATFORM_DOMAIN="example.test"),
        audit_chain=audit,  # type: ignore[arg-type]
    )

    memberships = await service.list_for_user(
        {"sub": str(user_id), "tenant_id": str(current_tenant_id)}
    )

    assert session.calls[0] == {"user_id": str(user_id)}
    assert session.calls[1] == {"email": "admin@example.com"}
    assert [entry.tenant_slug for entry in memberships] == ["default", "acme"]
    assert memberships[0].role is None
    assert memberships[0].is_current_tenant is True
    assert memberships[0].login_url == "https://app.example.test/login"
    assert memberships[1].role == "workspace_admin"
    assert memberships[1].login_url == "https://acme.example.test/login"
    assert audit.entries[-1]["event_type"] == "accounts.memberships.listed"
    assert audit.entries[-1]["tenant_id"] == current_tenant_id


@pytest.mark.asyncio
async def test_memberships_service_uses_context_tenant_and_router_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context_tenant_id = uuid4()
    auth_tenant_id = uuid4()
    user_id = uuid4()
    token = current_tenant.set(SimpleNamespace(id=context_tenant_id))
    session = _MembershipSession([])
    service = MembershipsService(
        platform_staff_session=session,  # type: ignore[arg-type]
        settings=PlatformSettings(),
    )
    try:
        assert service._current_tenant_id({"tenant_id": str(auth_tenant_id)}) == context_tenant_id
    finally:
        current_tenant.reset(token)
    assert service._current_tenant_id({}) == UUID("00000000-0000-0000-0000-000000000001")
    assert await service._resolve_email({"email": "ADMIN@example.COM"}) == "admin@example.com"

    empty_service = MembershipsService(
        platform_staff_session=_MembershipSession([], lookup_rows=[]),  # type: ignore[arg-type]
        settings=PlatformSettings(),
    )
    assert await empty_service._resolve_email({"sub": str(user_id)}) == ""
    assert await empty_service._append_audit(context_tenant_id, {}) is None

    entry = MembershipEntry(
        tenant_id=context_tenant_id,
        tenant_slug="default",
        tenant_kind="platform",
        tenant_display_name="Default",
        user_id_within_tenant=user_id,
        role="member",
        is_current_tenant=True,
        login_url="https://app.example.test/login",
    )

    class RouterService:
        async def list_for_user(self, current_user: dict[str, object]) -> list[MembershipEntry]:
            assert current_user == {"sub": str(user_id)}
            return [entry]

    monkeypatch.setattr(memberships_router, "MembershipsService", lambda **_kwargs: RouterService())
    monkeypatch.setattr(memberships_router, "build_audit_chain_service", lambda *_args: None)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(clients={}, settings=None)))
    response = await memberships_router.list_memberships(
        request,
        {"sub": str(user_id)},
        object(),  # type: ignore[arg-type]
    )

    assert response == MembershipsListResponse(memberships=[entry], count=1)
    assert memberships_router._producer(request) is None
