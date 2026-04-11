from __future__ import annotations

from platform.auth.rbac import RBACEngine
from platform.common.exceptions import PolicyViolationError
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.auth_support import RecordingProducer


class FakeRBACRepository:
    def __init__(self, permissions, user_roles) -> None:
        self.permissions = permissions
        self.user_roles = user_roles

    async def get_all_role_permissions(self):
        return self.permissions

    async def get_user_roles(self, user_id, workspace_id):
        del user_id, workspace_id
        return self.user_roles


@pytest.mark.asyncio
async def test_rbac_allows_matching_workspace_permission(monkeypatch) -> None:
    workspace_id = uuid4()
    repository = FakeRBACRepository(
        permissions=[
            SimpleNamespace(
                role="viewer",
                resource_type="agent",
                action="read",
                scope="workspace",
            )
        ],
        user_roles=[SimpleNamespace(role="viewer", workspace_id=workspace_id)],
    )
    engine = RBACEngine()
    monkeypatch.setattr("platform.auth.rbac.AuthRepository", lambda db: repository)

    result = await engine.check_permission(
        user_id=uuid4(),
        resource_type="agent",
        action="read",
        workspace_id=workspace_id,
        db=object(),
        redis_client=object(),
    )

    assert result.allowed is True
    assert result.role == "viewer"


@pytest.mark.asyncio
async def test_rbac_denies_missing_permission_and_emits_event(monkeypatch) -> None:
    workspace_id = uuid4()
    producer = RecordingProducer()
    repository = FakeRBACRepository(
        permissions=[
            SimpleNamespace(
                role="viewer",
                resource_type="agent",
                action="read",
                scope="workspace",
            )
        ],
        user_roles=[SimpleNamespace(role="viewer", workspace_id=workspace_id)],
    )
    engine = RBACEngine()
    monkeypatch.setattr("platform.auth.rbac.AuthRepository", lambda db: repository)

    result = await engine.check_permission(
        user_id=uuid4(),
        resource_type="agent",
        action="write",
        workspace_id=workspace_id,
        db=object(),
        redis_client=object(),
        producer=producer,
    )

    assert result.allowed is False
    assert result.reason == "rbac_denied"
    assert producer.events[0]["event_type"] == "auth.permission.denied"


@pytest.mark.asyncio
async def test_rbac_denies_when_user_has_no_roles(monkeypatch) -> None:
    producer = RecordingProducer()
    repository = FakeRBACRepository(permissions=[], user_roles=[])
    engine = RBACEngine()
    monkeypatch.setattr("platform.auth.rbac.AuthRepository", lambda db: repository)

    result = await engine.check_permission(
        user_id=uuid4(),
        resource_type="agent",
        action="read",
        workspace_id=uuid4(),
        db=object(),
        redis_client=object(),
        producer=producer,
    )

    assert result.allowed is False
    assert result.reason == "rbac_denied"
    assert producer.events[0]["event_type"] == "auth.permission.denied"


@pytest.mark.asyncio
async def test_rbac_superadmin_bypasses_checks(monkeypatch) -> None:
    repository = FakeRBACRepository(
        permissions=[],
        user_roles=[SimpleNamespace(role="superadmin", workspace_id=None)],
    )
    engine = RBACEngine()
    monkeypatch.setattr("platform.auth.rbac.AuthRepository", lambda db: repository)

    result = await engine.check_permission(
        user_id=uuid4(),
        resource_type="anything",
        action="delete",
        workspace_id=uuid4(),
        db=object(),
        redis_client=object(),
    )

    assert result.allowed is True
    assert result.scope == "global"


@pytest.mark.asyncio
async def test_rbac_evaluates_multiple_roles(monkeypatch) -> None:
    workspace_id = uuid4()
    repository = FakeRBACRepository(
        permissions=[
            SimpleNamespace(role="viewer", resource_type="agent", action="read", scope="workspace"),
            SimpleNamespace(
                role="creator",
                resource_type="agent",
                action="write",
                scope="workspace",
            ),
        ],
        user_roles=[
            SimpleNamespace(role="viewer", workspace_id=workspace_id),
            SimpleNamespace(role="creator", workspace_id=workspace_id),
        ],
    )
    engine = RBACEngine()
    monkeypatch.setattr("platform.auth.rbac.AuthRepository", lambda db: repository)

    result = await engine.check_permission(
        user_id=uuid4(),
        resource_type="agent",
        action="write",
        workspace_id=workspace_id,
        db=object(),
        redis_client=object(),
    )

    assert result.allowed is True
    assert result.role == "creator"


@pytest.mark.asyncio
async def test_rbac_applies_purpose_check_after_role_match(monkeypatch) -> None:
    workspace_id = uuid4()
    repository = FakeRBACRepository(
        permissions=[
            SimpleNamespace(
                role="agent",
                resource_type="execution",
                action="write",
                scope="own",
            )
        ],
        user_roles=[SimpleNamespace(role="agent", workspace_id=workspace_id)],
    )
    engine = RBACEngine()
    monkeypatch.setattr("platform.auth.rbac.AuthRepository", lambda db: repository)

    with pytest.raises(PolicyViolationError):
        await engine.check_permission(
            user_id=uuid4(),
            resource_type="execution",
            action="write",
            workspace_id=workspace_id,
            db=object(),
            redis_client=object(),
            identity_type="agent",
            agent_purpose="retrieval",
        )


def test_workspace_match_static_paths() -> None:
    workspace_id = uuid4()

    assert RBACEngine._workspace_matches(None, workspace_id, "global") is True
    assert RBACEngine._workspace_matches(workspace_id, None, "workspace") is False
    assert RBACEngine._workspace_matches(None, workspace_id, "workspace") is True
