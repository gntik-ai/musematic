from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.common.exceptions import AuthorizationError, NotFoundError
from platform.incident_response.schemas import IncidentRef, IncidentSeverity
from platform.status_page.schemas import SourceKind
from platform.testing import router_e2e
from platform.testing.schemas_e2e import (
    ChaosKillPodItem,
    ChaosKillPodRequest,
    ChaosKillPodResponse,
    ChaosPartitionRequest,
    ChaosPartitionResponse,
    E2EUserProvisionRequest,
    KafkaEventRecord,
    KafkaEventsResponse,
    MockLLMClearRequest,
    MockLLMRateLimitRequest,
    MockLLMSetRequest,
    ResetRequest,
    ResetResponse,
    SeedRequest,
    SeedResponse,
)
from types import SimpleNamespace
from uuid import uuid4

import pytest


class FixedDateTime:
    @staticmethod
    def now(tz):
        return datetime(2026, 4, 21, 12, 0, tzinfo=tz)


class _RedisRawStub:
    def __init__(self) -> None:
        self.values: dict[str, bytes | str | None] = {}
        self.keys = ["accounts:signup:ip:1", "accounts:signup:email:dev"]
        self.deleted: tuple[object, ...] = ()

    async def scan_iter(self, *, match: str, count: int):
        assert match == "accounts:signup:*"
        assert count == 100
        for key in self.keys:
            yield key

    async def delete(self, *keys: object) -> None:
        self.deleted = keys

    async def get(self, key: str) -> bytes | str | None:
        return self.values.get(key)


class _RedisWrapperStub:
    def __init__(self) -> None:
        self.raw = _RedisRawStub()

    async def _get_client(self) -> _RedisRawStub:
        return self.raw


def _request_with_state() -> tuple[SimpleNamespace, PlatformSettings, _RedisWrapperStub]:
    settings = PlatformSettings(feature_e2e_mode=True)
    redis_client = _RedisWrapperStub()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={"redis": redis_client},
            )
        )
    )
    return request, settings, redis_client


def test_role_and_scope_helpers_cover_supported_inputs() -> None:
    assert router_e2e._role_names(
        {"roles": [{"role": "platform_admin"}, {"role": None}, "skip"]}
    ) == {"platform_admin"}
    assert router_e2e._scopes({"scopes": "e2e admin"}) == {"e2e", "admin"}
    assert router_e2e._scopes({"scopes": ["e2e", "admin"]}) == {"e2e", "admin"}
    assert router_e2e._scopes({"scopes": {"unexpected": True}}) == set()


def test_require_admin_or_e2e_scope_accepts_expected_callers() -> None:
    admin = {"roles": [{"role": "platform_admin"}]}
    scoped = {"roles": [], "scopes": "e2e"}

    assert router_e2e.require_admin_or_e2e_scope(admin) is admin
    assert router_e2e.require_admin_or_e2e_scope(scoped) is scoped


def test_require_admin_or_e2e_scope_rejects_unauthorized_callers() -> None:
    with pytest.raises(AuthorizationError) as excinfo:
        router_e2e.require_admin_or_e2e_scope({"roles": [{"role": "viewer"}], "scopes": []})

    assert excinfo.value.code == "PERMISSION_DENIED"


def test_require_operator_or_e2e_scope_paths() -> None:
    operator = {"roles": [{"role": "operator"}], "scopes": []}
    workspace_admin = {"roles": [{"role": "workspace_admin"}], "scopes": []}
    scoped = {"roles": [], "scopes": ["e2e"]}

    assert router_e2e.require_operator_or_e2e_scope(operator) is operator
    assert router_e2e.require_operator_or_e2e_scope(workspace_admin) is workspace_admin
    assert router_e2e.require_operator_or_e2e_scope(scoped) is scoped
    with pytest.raises(AuthorizationError):
        router_e2e.require_operator_or_e2e_scope({"roles": [{"role": "viewer"}]})


@pytest.mark.asyncio
async def test_router_e2e_endpoint_functions_delegate_to_services(monkeypatch) -> None:
    request, settings, redis_client = _request_with_state()
    captured: dict[str, object] = {}

    class FakeSeedService:
        async def seed(self, scope: str) -> SeedResponse:
            captured["seed"] = scope
            return SeedResponse(seeded={scope: 2}, skipped={scope: 1}, duration_ms=4)

    class FakeResetService:
        async def reset(self, scope: str, *, include_baseline: bool) -> ResetResponse:
            captured["reset"] = (scope, include_baseline)
            return ResetResponse(
                deleted={scope: 3}, preserved_baseline=not include_baseline, duration_ms=5
            )

    class FakeChaosService:
        async def kill_pod(
            self, namespace: str, label_selector: str, count: int
        ) -> ChaosKillPodResponse:
            captured["kill_pod"] = (namespace, label_selector, count)
            return ChaosKillPodResponse(
                killed=[
                    ChaosKillPodItem(
                        pod="pod-1",
                        namespace=namespace,
                        at=datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
                    )
                ],
                not_found=0,
            )

        async def partition_network(
            self,
            from_namespace: str,
            to_namespace: str,
            ttl_seconds: int,
        ) -> ChaosPartitionResponse:
            captured["partition_network"] = (from_namespace, to_namespace, ttl_seconds)
            applied_at = datetime(2026, 4, 21, 9, 5, tzinfo=UTC)
            return ChaosPartitionResponse(
                network_policy_name="e2e-partition-1",
                applied_at=applied_at,
                expires_at=applied_at,
            )

    class FakeMockLLMService:
        async def set_rate_limit_error(self, prompt_pattern: str, count: int) -> None:
            captured["rate_limit"] = (prompt_pattern, count)

        async def set_response(
            self,
            prompt_pattern: str,
            response: str,
            streaming_chunks: list[str] | None,
        ) -> dict[str, int]:
            captured["mock_llm"] = (prompt_pattern, response, streaming_chunks)
            return {"agent_response": 7}

        async def get_calls(
            self,
            *,
            pattern: str | None,
            since: str | None,
        ) -> list[dict[str, str]]:
            captured["mock_calls"] = (pattern, since)
            return [{"prompt": pattern or "*", "since": since or ""}]

        async def clear_queue(self, prompt_pattern: str | None) -> None:
            captured["clear_mock"] = prompt_pattern

    class FakeKafkaObserver:
        def __init__(self, observed_settings: PlatformSettings) -> None:
            captured["observer_settings"] = observed_settings

        async def get_events(self, **kwargs) -> KafkaEventsResponse:
            captured["kafka_events"] = kwargs
            return KafkaEventsResponse(
                events=[
                    KafkaEventRecord(
                        topic=kwargs["topic"],
                        partition=0,
                        offset=12,
                        key=kwargs["key"],
                        timestamp=kwargs["since"],
                        headers={"trace_id": "abc"},
                        payload={"event_type": "checkpoint.created"},
                    )
                ],
                count=1,
            )

    monkeypatch.setattr(router_e2e, "SeedService", FakeSeedService)
    monkeypatch.setattr(router_e2e, "ResetService", FakeResetService)
    monkeypatch.setattr(router_e2e, "ChaosService", FakeChaosService)

    def build_fake_mock_llm_service(client: object) -> FakeMockLLMService:
        captured["redis"] = client
        return FakeMockLLMService()

    monkeypatch.setattr(router_e2e, "build_mock_llm_service", build_fake_mock_llm_service)
    monkeypatch.setattr(router_e2e, "KafkaObserver", FakeKafkaObserver)
    monkeypatch.setattr(router_e2e, "datetime", FixedDateTime)

    current_user = {"roles": [{"role": "platform_admin"}]}
    since = datetime(2026, 4, 21, 8, 0, tzinfo=UTC)

    seed_response = await router_e2e.seed(SeedRequest(scope="users"), request, current_user)
    reset_response = await router_e2e.reset(
        ResetRequest(scope="workspaces", include_baseline=True),
        request,
        current_user,
    )
    kill_response = await router_e2e.kill_pod(
        ChaosKillPodRequest(
            namespace="platform-execution",
            label_selector="app=worker",
            count=1,
        ),
        current_user,
    )
    partition_response = await router_e2e.partition_network(
        ChaosPartitionRequest(
            from_namespace="platform-execution",
            to_namespace="platform-data",
            ttl_seconds=30,
        ),
        current_user,
    )
    mock_response = await router_e2e.set_mock_llm_response(
        MockLLMSetRequest(
            prompt_pattern="agent_response",
            response="ok",
            streaming_chunks=["o", "k"],
        ),
        request,
        current_user,
    )
    rate_response = await router_e2e.set_mock_llm_rate_limit(
        MockLLMRateLimitRequest(prompt_pattern="slow", count=3),
        request,
        current_user,
    )
    calls_response = await router_e2e.get_mock_llm_calls(
        request,
        pattern="slow",
        since=since,
        current_user=current_user,
    )
    await router_e2e.clear_mock_llm(
        MockLLMClearRequest(prompt_pattern="slow"),
        request,
        current_user,
    )
    failure_response = await router_e2e.inject_failure(
        router_e2e.SyntheticFailureInjectRequest(
            correlation_id="corr-1",
            service="control-plane",
            error_message="synthetic failure",
            trace_id="trace-1",
        ),
        current_user,
    )
    kafka_response = await router_e2e.kafka_events(
        request,
        topic="execution.events",
        since=since,
        until=None,
        limit=5,
        key="trace-1",
        current_user=current_user,
    )

    assert seed_response.seeded == {"users": 2}
    assert reset_response.deleted == {"workspaces": 3}
    assert kill_response.killed[0].pod == "pod-1"
    assert partition_response.network_policy_name == "e2e-partition-1"
    assert mock_response.queue_depth == {"agent_response": 7}
    assert rate_response.remaining == 3
    assert calls_response.calls == [{"prompt": "slow", "since": since.isoformat()}]
    assert captured["clear_mock"] == "slow"
    assert failure_response.service == "control-plane"
    assert kafka_response.count == 1
    assert captured["seed"] == "users"
    assert captured["reset"] == ("workspaces", True)
    assert captured["kill_pod"] == ("platform-execution", "app=worker", 1)
    assert captured["partition_network"] == ("platform-execution", "platform-data", 30)
    assert captured["redis"] is redis_client
    assert captured["mock_llm"] == ("agent_response", "ok", ["o", "k"])
    assert captured["rate_limit"] == ("slow", 3)
    assert captured["mock_calls"] == ("slow", since.isoformat())
    assert captured["observer_settings"] is settings
    assert captured["kafka_events"] == {
        "topic": "execution.events",
        "since": since,
        "until": datetime(2026, 4, 21, 12, 0, tzinfo=UTC),
        "limit": 5,
        "key": "trace-1",
    }


@pytest.mark.asyncio
async def test_router_e2e_account_and_incident_helpers(monkeypatch) -> None:
    request, settings, redis_client = _request_with_state()
    current_user = {"roles": [{"role": "platform_admin"}]}
    settings.accounts.signup_mode = "open"

    signup = await router_e2e.set_account_signup_mode(
        router_e2e.E2ESignupModeRequest(signup_mode="invite_only"),
        request,
        current_user,
    )
    assert signup == {"previous": "open", "current": "invite_only"}
    assert settings.accounts.signup_mode == "invite_only"

    response = await router_e2e.clear_account_signup_rate_limits(request, current_user)
    assert response.status_code == 204
    assert redis_client.raw.deleted == tuple(redis_client.raw.keys)

    redis_client.raw.values["e2e:accounts:verification-token:dev@example.test"] = b"verify-token"
    assert await router_e2e.get_account_verification_token(
        request,
        email="DEV@EXAMPLE.TEST",
        current_user=current_user,
    ) == {"email": "dev@example.test", "token": "verify-token"}

    empty_tokens = await router_e2e.get_status_subscription_tokens(
        request,
        email=" Dev@Example.TEST ",
        current_user=current_user,
    )
    assert empty_tokens == {
        "email": "dev@example.test",
        "confirmation_token": None,
        "unsubscribe_token": None,
    }
    redis_client.raw.values["e2e:status-subscriptions:tokens:dev@example.test"] = (
        '{"confirmation_token": "confirm", "unsubscribe_token": "unsubscribe"}'
    )
    tokens = await router_e2e.get_status_subscription_tokens(
        request,
        email="dev@example.test",
        current_user=current_user,
    )
    assert tokens["confirmation_token"] == "confirm"
    assert tokens["unsubscribe_token"] == "unsubscribe"

    class DispatchSessionStub:
        def __init__(self) -> None:
            self.calls: list[tuple[object, object | None]] = []

        async def execute(self, statement: object, params: object | None = None):
            self.calls.append((statement, params))
            return SimpleNamespace(scalar_one=lambda: 2)

    dispatch_session = DispatchSessionStub()
    dispatches = await router_e2e.get_status_subscription_dispatches(
        email=" Dev@Example.TEST ",
        event_kind="incident.created",
        outcome="sent",
        current_user=current_user,
        session=dispatch_session,  # type: ignore[arg-type]
    )
    assert dispatches == {
        "email": "dev@example.test",
        "event_kind": "incident.created",
        "outcome": "sent",
        "count": 2,
    }
    assert dispatch_session.calls[0][1] == {
        "email": "dev@example.test",
        "event_kind": "incident.created",
        "outcome": "sent",
    }

    class SessionStub:
        def __init__(self, user_id: object | None = uuid4()) -> None:
            self.user_id = user_id
            self.calls: list[tuple[object, object | None]] = []

        async def execute(self, statement: object, params: object | None = None):
            self.calls.append((statement, params))
            return SimpleNamespace(scalar_one_or_none=lambda: self.user_id)

    expired = await router_e2e.create_expired_account_verification_token(
        router_e2e.E2EExpiredVerificationTokenRequest(email=" Dev@Example.TEST "),
        current_user,
        SessionStub(),
    )
    assert expired["email"] == "dev@example.test"
    assert expired["token"]
    with pytest.raises(NotFoundError):
        await router_e2e.create_expired_account_verification_token(
            router_e2e.E2EExpiredVerificationTokenRequest(email="missing@example.test"),
            current_user,
            SessionStub(user_id=None),
        )

    provision_session = SessionStub()
    user_id = uuid4()
    provisioned = await router_e2e.provision_user(
        E2EUserProvisionRequest(
            id=user_id,
            email="pending@e2e.test",
            status="pending_approval",
            roles=["platform_admin", "operator"],
        ),
        provision_session,
    )
    assert provisioned.id == user_id
    assert len(provision_session.calls) == 6

    class IncidentServiceStub:
        def __init__(self) -> None:
            self.signals = []
            self.resolved: tuple[object, object | None, bool] | None = None

        async def create_from_signal(self, signal) -> IncidentRef:
            self.signals.append(signal)
            return IncidentRef(incident_id=uuid4())

        async def resolve(self, incident_id, *, resolved_at, auto_resolved):
            self.resolved = (incident_id, resolved_at, auto_resolved)
            return SimpleNamespace(
                id=incident_id,
                title="Custom title",
                severity=IncidentSeverity.high,
                runbook_scenario="status_page",
            )

    class StatusPageServiceStub:
        def __init__(self) -> None:
            self.snapshots: list[SourceKind] = []
            self.events: list[tuple[str, dict[str, object]]] = []

        async def compose_current_snapshot(self, *, source_kind: SourceKind) -> None:
            self.snapshots.append(source_kind)

        async def dispatch_event(self, event_kind: str, payload: dict[str, object]) -> int:
            self.events.append((event_kind, payload))
            return 1

    incident_service = IncidentServiceStub()
    status_page_service = StatusPageServiceStub()
    seeded = await router_e2e.seed_incident(
        "status-page",
        current_user,
        incident_service,  # type: ignore[arg-type]
    )
    triggered = await router_e2e.trigger_incident(
        router_e2e.E2EIncidentTriggerRequest(
            scenario="status-page",
            severity=IncidentSeverity.high,
            title="Custom title",
            description="Custom description",
        ),
        current_user,
        incident_service,  # type: ignore[arg-type]
        status_page_service,  # type: ignore[arg-type]
    )
    incident_id = uuid4()
    resolved = await router_e2e.resolve_incident(
        router_e2e.E2EIncidentResolveRequest(
            incident_id=incident_id,
            auto_resolved=True,
        ),
        current_user,
        incident_service,  # type: ignore[arg-type]
        status_page_service,  # type: ignore[arg-type]
    )
    assert seeded.incident_id
    assert triggered.incident_id
    assert incident_service.signals[0].runbook_scenario == "status_page"
    assert incident_service.signals[1].title == "Custom title"
    assert resolved.incident_id == incident_id
    assert incident_service.resolved == (incident_id, None, True)
    assert status_page_service.snapshots == [SourceKind.kafka, SourceKind.kafka]
    assert status_page_service.events == [
        (
            "incident.created",
            {
                "incident_id": str(triggered.incident_id),
                "title": "Custom title",
                "severity": "high",
                "components_affected": ["control-plane-api"],
            },
        ),
        (
            "incident.resolved",
            {
                "incident_id": str(incident_id),
                "title": "Custom title",
                "severity": "high",
                "components_affected": ["control-plane-api"],
            },
        ),
    ]
