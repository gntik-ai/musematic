from __future__ import annotations

from pathlib import Path
from platform.accounts import onboarding_router
from platform.accounts.exceptions import DefaultWorkspaceNotProvisionedError
from platform.accounts.models import UserOnboardingState
from platform.accounts.onboarding import OnboardingWizardService
from platform.accounts.schemas import (
    OnboardingStateView,
    OnboardingStepFirstAgent,
    OnboardingStepInvitations,
    OnboardingStepTour,
    OnboardingStepWorkspaceName,
)
from platform.common.tenant_context import current_tenant
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tests.auth_support import RecordingProducer


class _ScalarResult:
    def __init__(self, value: object | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object | None:
        return self.value


class _Session:
    def __init__(self, user: object | None = None) -> None:
        self.user = user
        self.added: list[object] = []
        self.results: list[object | None] = []
        self.flushed = 0

    def add(self, instance: object) -> None:
        if isinstance(instance, UserOnboardingState):
            _seed_state_defaults(instance)
        self.added.append(instance)

    async def flush(self) -> None:
        self.flushed += 1

    async def get(self, _model: type[object], _id: object) -> object | None:
        return self.user

    async def execute(self, _statement: object) -> _ScalarResult:
        return _ScalarResult(self.results.pop(0) if self.results else None)


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, object]] = []

    async def append(self, *_args: object, **kwargs: object) -> None:
        self.entries.append(kwargs)


def _seed_state_defaults(state: UserOnboardingState) -> UserOnboardingState:
    if getattr(state, "id", None) is None:
        state.id = uuid4()
    state.step_workspace_named = bool(state.step_workspace_named)
    state.step_invitations_sent_or_skipped = bool(state.step_invitations_sent_or_skipped)
    state.step_first_agent_created_or_skipped = bool(state.step_first_agent_created_or_skipped)
    state.step_tour_started_or_skipped = bool(state.step_tour_started_or_skipped)
    state.last_step_attempted = state.last_step_attempted or "workspace_named"
    return state


def _state(*, tenant_id=None, user_id=None) -> UserOnboardingState:
    return _seed_state_defaults(
        UserOnboardingState(user_id=user_id or uuid4(), tenant_id=tenant_id or uuid4())
    )


def _workspace(owner_id):
    return SimpleNamespace(id=uuid4(), owner_id=owner_id, is_default=True, name="Starter")


def _service(session: _Session, *, first_agent: bool = True):
    producer = RecordingProducer()
    audit = _Audit()
    settings = SimpleNamespace(
        feature_flags={"FEATURE_FIRST_AGENT_ONBOARDING": first_agent},
    )
    return (
        OnboardingWizardService(
            session=session,  # type: ignore[arg-type]
            settings=settings,  # type: ignore[arg-type]
            producer=producer,
            audit_chain=audit,  # type: ignore[arg-type]
        ),
        producer,
        audit,
    )


def test_onboarding_service_contract_and_metrics_are_present() -> None:
    source = Path("src/platform/accounts/onboarding.py").read_text(encoding="utf-8")

    for method in (
        "get_or_create_state",
        "advance_step",
        "dismiss",
        "relaunch",
        "is_first_agent_step_available",
    ):
        assert f"async def {method}" in source
    assert "accounts_onboarding_step_advanced_total" in source
    assert "accounts_onboarding_dismissed_total" in source
    assert "accounts.onboarding.step_advanced" in source
    assert "accounts.onboarding.dismissed" in source


@pytest.mark.asyncio
async def test_onboarding_get_or_create_advance_dismiss_and_relaunch() -> None:
    user_id = uuid4()
    tenant_id = uuid4()
    user = SimpleNamespace(id=user_id, tenant_id=tenant_id)
    session = _Session(user)
    service, producer, audit = _service(session, first_agent=False)
    workspace = _workspace(user_id)
    session.results = [None, workspace]

    view = await service.get_or_create_state(user_id)

    state = session.added[0]
    assert isinstance(state, UserOnboardingState)
    assert view.default_workspace_id == workspace.id
    assert view.default_workspace_name == "Starter"

    session.results = [state, workspace]
    result = await service.advance_step(
        user_id,
        "workspace-name",
        OnboardingStepWorkspaceName(workspace_name="Launch"),
    )
    assert result == {"next_step": "invitations"}
    assert workspace.name == "Launch"
    assert producer.events[-1]["event_type"] == "accounts.onboarding.step_advanced"
    assert audit.entries[-1]["event_type"] == "accounts.onboarding.step_advanced"

    session.results = [state]
    result = await service.advance_step(
        user_id,
        "invitations",
        OnboardingStepInvitations(invitations=[]),
    )
    assert result == {"next_step": "tour", "invitations_sent": 0}

    session.results = [state]
    assert await service.advance_step(
        user_id,
        "first-agent",
        OnboardingStepFirstAgent(skipped=True),
    ) == {"next_step": "tour"}

    session.results = [state]
    assert await service.advance_step(
        user_id,
        "tour",
        OnboardingStepTour(started=False),
    ) == {"next_step": "done"}

    session.results = [state]
    dismissed = await service.dismiss(user_id)
    assert dismissed["dismissed_at"] == state.dismissed_at
    assert producer.events[-1]["event_type"] == "accounts.onboarding.dismissed"

    state.step_tour_started_or_skipped = False
    session.results = [state, workspace]
    relaunched = await service.relaunch(user_id)
    assert relaunched.last_step_attempted == "tour"
    assert producer.events[-1]["event_type"] == "accounts.onboarding.relaunched"


@pytest.mark.asyncio
async def test_onboarding_error_and_feature_flag_edges() -> None:
    user_id = uuid4()
    state = _state(user_id=user_id)
    session = _Session(SimpleNamespace(id=user_id, tenant_id=state.tenant_id))
    service, _producer, _audit = _service(session)

    assert await service.is_first_agent_step_available() is True
    session.results = [state]
    with pytest.raises(ValueError, match="unknown onboarding step"):
        await service.advance_step(
            user_id,
            "unknown",
            OnboardingStepTour(started=False),
        )

    session.results = [state, None]
    with pytest.raises(DefaultWorkspaceNotProvisionedError):
        await service.advance_step(
            user_id,
            "workspace-name",
            OnboardingStepWorkspaceName(workspace_name="Missing"),
        )

    await service._rename_default_workspace(user_id, object())


@pytest.mark.asyncio
async def test_onboarding_helper_edges_use_context_and_step_order() -> None:
    tenant_id = uuid4()
    session = _Session()
    service, _producer, _audit = _service(session)
    token = current_tenant.set(SimpleNamespace(id=tenant_id))
    try:
        assert service._tenant_id(None) == tenant_id
    finally:
        current_tenant.reset(token)

    with pytest.raises(LookupError):
        service._tenant_id(None)

    state = _state()
    assert service._first_incomplete_step(state) == "workspace_named"
    state.step_workspace_named = True
    assert service._first_incomplete_step(state) == "invitations"
    state.step_invitations_sent_or_skipped = True
    assert service._first_incomplete_step(state) == "first_agent"
    state.step_first_agent_created_or_skipped = True
    assert service._first_incomplete_step(state) == "tour"
    state.step_tour_started_or_skipped = True
    assert service._first_incomplete_step(state) == "done"

    service_without_audit = OnboardingWizardService(
        session=session,  # type: ignore[arg-type]
        settings=SimpleNamespace(feature_flags={}),  # type: ignore[arg-type]
        audit_chain=None,
    )
    assert await service_without_audit._append_audit("event", tenant_id, {}) is None


@pytest.mark.asyncio
async def test_onboarding_router_delegates_all_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    tenant_id = uuid4()
    view = OnboardingStateView(
        user_id=user_id,
        tenant_id=tenant_id,
        step_workspace_named=False,
        step_invitations_sent_or_skipped=False,
        step_first_agent_created_or_skipped=False,
        step_tour_started_or_skipped=False,
        last_step_attempted="workspace_named",
        dismissed_at=None,
        first_agent_step_available=True,
        default_workspace_id=None,
        default_workspace_name=None,
    )

    class RouterService:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        async def get_or_create_state(self, received_user_id: object) -> OnboardingStateView:
            self.calls.append(("state", received_user_id))
            return view

        async def advance_step(
            self,
            received_user_id: object,
            step: str,
            payload: object,
        ) -> dict[str, object]:
            self.calls.append((step, payload))
            return {"next_step": step, "user_id": str(received_user_id)}

        async def dismiss(self, received_user_id: object) -> dict[str, object]:
            self.calls.append(("dismiss", received_user_id))
            return {"dismissed_at": "now"}

        async def relaunch(self, received_user_id: object) -> OnboardingStateView:
            self.calls.append(("relaunch", received_user_id))
            return view

    service = RouterService()
    monkeypatch.setattr(onboarding_router, "_service", lambda _request, _session: service)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(clients={}, settings=None)))
    current_user = {"sub": str(user_id)}

    assert await onboarding_router.get_state(request, current_user, object()) is view
    assert await onboarding_router.step_workspace_name(
        OnboardingStepWorkspaceName(workspace_name="Launch"),
        request,
        current_user,
        object(),
    ) == {"next_step": "workspace-name", "user_id": str(user_id)}
    assert await onboarding_router.step_invitations(
        OnboardingStepInvitations(invitations=[]),
        request,
        current_user,
        object(),
    ) == {"next_step": "invitations", "user_id": str(user_id)}
    assert await onboarding_router.step_first_agent(
        OnboardingStepFirstAgent(skipped=True),
        request,
        current_user,
        object(),
    ) == {"next_step": "first-agent", "user_id": str(user_id)}
    assert await onboarding_router.step_tour(
        OnboardingStepTour(started=True),
        request,
        current_user,
        object(),
    ) == {"next_step": "tour", "user_id": str(user_id)}
    assert await onboarding_router.dismiss(request, current_user, object()) == {
        "dismissed_at": "now"
    }
    assert await onboarding_router.relaunch(request, current_user, object()) is view
    assert [call[0] for call in service.calls] == [
        "state",
        "workspace-name",
        "invitations",
        "first-agent",
        "tour",
        "dismiss",
        "relaunch",
    ]
