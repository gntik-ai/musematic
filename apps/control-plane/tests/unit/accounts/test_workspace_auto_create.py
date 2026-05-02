from __future__ import annotations

import builtins
from platform.accounts.jobs import workspace_auto_create
from types import SimpleNamespace
from uuid import uuid4

import pytest


class _MappingsResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def mappings(self) -> _MappingsResult:
        return self

    def all(self) -> list[dict[str, object]]:
        return self.rows


class _Session:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.committed = 0

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, _statement: object) -> _MappingsResult:
        return _MappingsResult(self.rows)

    async def commit(self) -> None:
        self.committed += 1


class _WorkspacesService:
    def __init__(self, **_kwargs: object) -> None:
        self.calls: list[tuple[object, str]] = []

    async def create_default_workspace(self, user_id: object, display_name: str) -> None:
        self.calls.append((user_id, display_name))
        if display_name == "Bad":
            raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_workspace_auto_create_retry_creates_available_workspaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    failing_user_id = uuid4()
    session = _Session(
        [
            {"id": user_id, "display_name": "Admin"},
            {"id": failing_user_id, "display_name": "Bad"},
        ]
    )
    service = _WorkspacesService()
    monkeypatch.setattr(workspace_auto_create.database, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(
        workspace_auto_create,
        "WorkspacesService",
        lambda **_kwargs: service,
    )
    monkeypatch.setattr(workspace_auto_create, "WorkspacesRepository", lambda _session: object())
    monkeypatch.setattr(workspace_auto_create, "SubscriptionsRepository", lambda _session: object())
    monkeypatch.setattr(workspace_auto_create, "PlansRepository", lambda _session: object())
    monkeypatch.setattr(
        workspace_auto_create,
        "SubscriptionService",
        lambda **_kwargs: object(),
    )
    app = SimpleNamespace(
        state=SimpleNamespace(settings=SimpleNamespace(), clients={"kafka": object()}),
    )

    await workspace_auto_create.run_workspace_auto_create_retry(app)

    assert session.committed == 1
    assert service.calls == [(user_id, "Admin"), (failing_user_id, "Bad")]


def test_workspace_auto_create_scheduler_handles_available_and_missing_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            settings=SimpleNamespace(SIGNUP_AUTO_CREATE_RETRY_SECONDS=42),
        ),
    )
    scheduler = workspace_auto_create.build_workspace_auto_create_retry(app)

    assert scheduler is not None

    real_import = builtins.__import__

    def blocked_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "apscheduler.schedulers.asyncio":
            raise ImportError("missing apscheduler")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    assert workspace_auto_create.build_workspace_auto_create_retry(app) is None
