from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.common.exceptions import AuthorizationError
from platform.testing import router_e2e
from platform.testing.schemas_e2e import (
    ChaosKillPodItem,
    ChaosKillPodRequest,
    ChaosKillPodResponse,
    ChaosPartitionRequest,
    ChaosPartitionResponse,
    KafkaEventRecord,
    KafkaEventsResponse,
    MockLLMSetRequest,
    ResetRequest,
    ResetResponse,
    SeedRequest,
    SeedResponse,
)
from types import SimpleNamespace

import pytest


class FixedDateTime:
    @staticmethod
    def now(tz):
        return datetime(2026, 4, 21, 12, 0, tzinfo=tz)


def _request_with_state() -> tuple[SimpleNamespace, PlatformSettings, object]:
    settings = PlatformSettings(feature_e2e_mode=True)
    redis_client = object()
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
        async def set_response(
            self,
            prompt_pattern: str,
            response: str,
            streaming_chunks: list[str] | None,
        ) -> dict[str, int]:
            captured["mock_llm"] = (prompt_pattern, response, streaming_chunks)
            return {"agent_response": 7}

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
    assert kafka_response.count == 1
    assert captured["seed"] == "users"
    assert captured["reset"] == ("workspaces", True)
    assert captured["kill_pod"] == ("platform-execution", "app=worker", 1)
    assert captured["partition_network"] == ("platform-execution", "platform-data", 30)
    assert captured["redis"] is redis_client
    assert captured["mock_llm"] == ("agent_response", "ok", ["o", "k"])
    assert captured["observer_settings"] is settings
    assert captured["kafka_events"] == {
        "topic": "execution.events",
        "since": since,
        "until": datetime(2026, 4, 21, 12, 0, tzinfo=UTC),
        "limit": 5,
        "key": "trace-1",
    }
