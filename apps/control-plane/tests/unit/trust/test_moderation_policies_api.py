from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from platform.common.exceptions import AuthorizationError
from platform.trust.models import ContentModerationPolicy
from platform.trust.routers import moderation_policies_router as router
from platform.trust.schemas import (
    Category,
    ModerationAction,
    ModerationPolicyCreateRequest,
    ModerationPolicyTestRequest,
)
from platform.trust.services.moderation_providers.base import ProviderVerdict
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest


class FakeSession:
    async def execute(self, *_args: object, **_kwargs: object) -> None:
        return None


class FakeRepo:
    def __init__(self, _session: object) -> None:
        self.policies: dict[UUID, ContentModerationPolicy] = {}
        self.created: list[ContentModerationPolicy] = []

    async def create_moderation_policy(
        self,
        policy: ContentModerationPolicy,
    ) -> ContentModerationPolicy:
        policy.id = uuid4()
        policy.version = policy.version or 1
        policy.active = True if policy.active is None else policy.active
        policy.created_at = datetime.now(UTC)
        policy.updated_at = policy.created_at
        self.policies[policy.id] = policy
        self.created.append(policy)
        return policy

    async def list_moderation_policy_versions(
        self,
        workspace_id: UUID,
    ) -> list[ContentModerationPolicy]:
        return [item for item in self.policies.values() if item.workspace_id == workspace_id]

    async def get_active_moderation_policy(
        self,
        workspace_id: UUID,
    ) -> ContentModerationPolicy | None:
        return next(
            (
                item
                for item in self.policies.values()
                if item.workspace_id == workspace_id and item.active
            ),
            None,
        )

    async def get_moderation_policy(self, policy_id: UUID) -> ContentModerationPolicy | None:
        return self.policies.get(policy_id)

    async def deactivate_moderation_policy(
        self,
        policy_id: UUID,
    ) -> ContentModerationPolicy | None:
        policy = self.policies.get(policy_id)
        if policy is not None:
            policy.active = False
        return policy


class ProviderStub:
    async def score(
        self,
        text: str,
        *,
        language: str | None,
        categories: set[str],
    ) -> ProviderVerdict:
        del text, language, categories
        return ProviderVerdict(provider="openai", scores={"toxicity": 0.99})


class ModeratorStub:
    providers = SimpleNamespace(get=lambda _name: ProviderStub())


def _request(workspace_id: UUID, *, audit: bool = False) -> Any:
    settings = SimpleNamespace(audit=SimpleNamespace()) if audit else None
    return SimpleNamespace(
        headers={"X-Workspace-ID": str(workspace_id)},
        app=SimpleNamespace(state=SimpleNamespace(clients={}, settings=settings)),
    )


def _admin(user_id: UUID | None = None) -> dict[str, Any]:
    return {"sub": str(user_id or uuid4()), "roles": [{"role": "workspace_admin"}]}


def _payload() -> ModerationPolicyCreateRequest:
    return ModerationPolicyCreateRequest(
        categories=[Category.toxicity],
        thresholds={Category.toxicity: 0.8},
        action_map={Category.toxicity: ModerationAction.block},
        primary_provider="openai",
        monthly_cost_cap_eur=Decimal("10.0"),
    )


@pytest.mark.asyncio
async def test_policy_router_role_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_id = uuid4()
    monkeypatch.setattr(router, "TrustRepository", FakeRepo)

    with pytest.raises(AuthorizationError):
        await router.create_policy(
            _payload(),
            _request(workspace_id),
            current_user={"sub": str(uuid4()), "roles": []},
            session=FakeSession(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_policy_router_version_bump_and_cross_workspace_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    other_workspace_id = uuid4()
    repo = FakeRepo(FakeSession())
    monkeypatch.setattr(router, "TrustRepository", lambda _session: repo)

    created = await router.create_policy(
        _payload(),
        _request(workspace_id),
        current_user=_admin(),
        session=FakeSession(),  # type: ignore[arg-type]
    )
    updated = await router.update_policy(
        created.id,
        _payload(),
        _request(workspace_id),
        current_user=_admin(),
        session=FakeSession(),  # type: ignore[arg-type]
    )

    assert created.version == 1
    assert updated.version == 2

    with pytest.raises(AuthorizationError):
        await router.get_policy(
            created.id,
            _request(other_workspace_id),
            current_user=_admin(),
            session=FakeSession(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_policy_test_mode_does_not_persist_and_audits_hash_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    repo = FakeRepo(FakeSession())
    audits: list[dict[str, Any]] = []
    monkeypatch.setattr(router, "TrustRepository", lambda _session: repo)
    monkeypatch.setattr(router, "build_audit_chain_service", lambda **_kwargs: object())

    async def fake_audit_hook(
        _service: object,
        _audit_event_id: object,
        _source: str,
        payload: dict[str, Any],
    ) -> None:
        audits.append(payload)

    monkeypatch.setattr(router, "audit_chain_hook", fake_audit_hook)

    created = await router.create_policy(
        _payload(),
        _request(workspace_id, audit=True),
        current_user=_admin(),
        session=FakeSession(),  # type: ignore[arg-type]
    )
    response = await router.evaluate_policy_sample(
        created.id,
        ModerationPolicyTestRequest(content="raw toxic sample"),
        _request(workspace_id, audit=True),
        current_user=_admin(),
        session=FakeSession(),  # type: ignore[arg-type]
        moderator=ModeratorStub(),  # type: ignore[arg-type]
    )

    assert response.persisted is False
    assert len(repo.created) == 1
    assert audits[-1]["action"] == "tested"
    assert audits[-1]["sample_input_hash"]
    assert "raw toxic sample" not in str(audits[-1])
