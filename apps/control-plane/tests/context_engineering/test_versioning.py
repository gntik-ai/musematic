from __future__ import annotations

from datetime import UTC, datetime
from platform.context_engineering.models import ContextProfileVersion
from platform.context_engineering.schemas import ProfileCreate
from platform.context_engineering.service import ContextEngineeringService
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeContextRepository:
    def __init__(self) -> None:
        self.session = FakeSession()
        self.profiles: dict[UUID, SimpleNamespace] = {}
        self.versions: dict[UUID, list[SimpleNamespace]] = {}
        self.cleared_defaults: list[UUID] = []

    async def clear_default_profiles(
        self,
        workspace_id: UUID,
        exclude_profile_id: UUID | None = None,
    ) -> None:
        del exclude_profile_id
        self.cleared_defaults.append(workspace_id)

    async def create_profile(self, **fields: object) -> SimpleNamespace:
        now = datetime.now(UTC)
        profile = SimpleNamespace(
            id=uuid4(),
            created_at=now,
            updated_at=now,
            **fields,
        )
        self.profiles[profile.id] = profile
        self.versions[profile.id] = []
        return profile

    async def get_profile(
        self,
        workspace_id: UUID,
        profile_id: UUID,
    ) -> SimpleNamespace | None:
        profile = self.profiles.get(profile_id)
        if profile is None or profile.workspace_id != workspace_id:
            return None
        return profile

    async def update_profile(
        self,
        profile: SimpleNamespace,
        **fields: object,
    ) -> SimpleNamespace:
        for key, value in fields.items():
            setattr(profile, key, value)
        profile.updated_at = datetime.now(UTC)
        return profile

    async def create_profile_version(
        self,
        *,
        profile_id: UUID,
        version_number: int,
        content_snapshot: dict[str, object],
        change_summary: str | None,
        created_by: UUID | None,
    ) -> SimpleNamespace:
        version = SimpleNamespace(
            id=uuid4(),
            profile_id=profile_id,
            version_number=version_number,
            content_snapshot=content_snapshot,
            change_summary=change_summary,
            created_by=created_by,
            created_at=datetime.now(UTC),
        )
        self.versions.setdefault(profile_id, []).append(version)
        return version

    async def latest_profile_version_number(self, profile_id: UUID) -> int:
        return max((item.version_number for item in self.versions.get(profile_id, [])), default=0)

    async def list_profile_versions(
        self,
        profile_id: UUID,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[SimpleNamespace], str | None]:
        versions = sorted(
            self.versions.get(profile_id, []),
            key=lambda item: item.version_number,
            reverse=True,
        )
        if cursor is not None:
            versions = [item for item in versions if item.version_number < int(cursor)]
        next_cursor = None
        if len(versions) > limit:
            versions = versions[:limit]
            next_cursor = str(versions[-1].version_number)
        return versions, next_cursor

    async def get_profile_version(
        self,
        profile_id: UUID,
        version_number: int,
    ) -> SimpleNamespace | None:
        for item in self.versions.get(profile_id, []):
            if item.version_number == version_number:
                return item
        return None


def _service(repository: FakeContextRepository) -> ContextEngineeringService:
    return ContextEngineeringService(
        repository=repository,  # type: ignore[arg-type]
        adapters={},
        quality_scorer=SimpleNamespace(),
        compactor=SimpleNamespace(),
        privacy_filter=SimpleNamespace(),
        object_storage=SimpleNamespace(),
        clickhouse_client=SimpleNamespace(),
        settings=SimpleNamespace(),
        event_producer=None,
    )


def _profile(name: str = "KYC Profile") -> ProfileCreate:
    return ProfileCreate(
        name=name,
        description="Context profile for creator preview tests.",
        quality_weights={"relevance": 0.8},
        privacy_overrides={"pii": "mask"},
        is_default=True,
    )


@pytest.mark.asyncio
async def test_create_profile_creates_initial_version_snapshot() -> None:
    repository = FakeContextRepository()
    service = _service(repository)
    workspace_id = uuid4()
    actor_id = uuid4()

    created = await service.create_profile(workspace_id, _profile(), actor_id)

    versions = repository.versions[created.id]
    assert [item.version_number for item in versions] == [1]
    assert versions[0].change_summary == "Initial profile creation"
    assert versions[0].content_snapshot["name"] == "KYC Profile"
    assert versions[0].content_snapshot["_schema_version"] == 1
    assert repository.session.commits == 1


@pytest.mark.asyncio
async def test_update_profile_creates_monotonic_version() -> None:
    repository = FakeContextRepository()
    service = _service(repository)
    workspace_id = uuid4()
    actor_id = uuid4()
    created = await service.create_profile(workspace_id, _profile(), actor_id)

    await service.update_profile(workspace_id, created.id, _profile("KYC Profile v2"), actor_id)

    versions = repository.versions[created.id]
    assert [item.version_number for item in versions] == [1, 2]
    assert versions[1].content_snapshot["name"] == "KYC Profile v2"
    assert versions[1].change_summary == "Profile updated"


@pytest.mark.asyncio
async def test_get_profile_versions_returns_cursor_paginated_history() -> None:
    repository = FakeContextRepository()
    service = _service(repository)
    workspace_id = uuid4()
    actor_id = uuid4()
    created = await service.create_profile(workspace_id, _profile(), actor_id)
    await service.update_profile(workspace_id, created.id, _profile("v2"), actor_id)
    await service.update_profile(workspace_id, created.id, _profile("v3"), actor_id)

    response = await service.get_profile_versions(
        workspace_id,
        created.id,
        actor_id,
        limit=2,
        cursor=None,
    )

    assert [item.version_number for item in response.versions] == [3, 2]
    assert response.next_cursor == "2"


@pytest.mark.asyncio
async def test_get_version_diff_reports_added_removed_and_modified_keys() -> None:
    repository = FakeContextRepository()
    service = _service(repository)
    workspace_id = uuid4()
    actor_id = uuid4()
    created = await service.create_profile(workspace_id, _profile(), actor_id)
    await repository.create_profile_version(
        profile_id=created.id,
        version_number=2,
        content_snapshot={"kept": "old", "removed": True},
        change_summary="manual",
        created_by=actor_id,
    )
    await repository.create_profile_version(
        profile_id=created.id,
        version_number=3,
        content_snapshot={"kept": "new", "added": 1},
        change_summary="manual",
        created_by=actor_id,
    )

    diff = await service.get_version_diff(
        workspace_id,
        created.id,
        actor_id,
        v1_number=2,
        v2_number=3,
    )

    assert diff.added == {"added": 1}
    assert diff.removed == {"removed": True}
    assert diff.modified == {"kept": {"old": "old", "new": "new"}}


@pytest.mark.asyncio
async def test_rollback_creates_new_version_without_mutating_target() -> None:
    repository = FakeContextRepository()
    service = _service(repository)
    workspace_id = uuid4()
    actor_id = uuid4()
    created = await service.create_profile(workspace_id, _profile(), actor_id)
    await service.update_profile(workspace_id, created.id, _profile("KYC Profile v2"), actor_id)
    target_before = dict(repository.versions[created.id][0].content_snapshot)

    rollback = await service.rollback_to_version(workspace_id, created.id, 1, actor_id)

    assert rollback.version_number == 3
    assert rollback.content_snapshot == target_before
    assert repository.versions[created.id][0].content_snapshot == target_before
    assert repository.profiles[created.id].name == target_before["name"]


def test_context_profile_version_has_unique_profile_version_constraint() -> None:
    constraint_names = {
        constraint.name for constraint in ContextProfileVersion.__table__.constraints
    }

    assert "uq_context_profile_versions_profile_version" in constraint_names


def test_context_profile_version_profile_fk_cascades_on_delete() -> None:
    foreign_keys = ContextProfileVersion.__table__.c.profile_id.foreign_keys

    assert any(fk.ondelete == "CASCADE" for fk in foreign_keys)
