from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from platform.admin import security_scheduler
from platform.common.clients.redis import MultiWindowRateLimitResult
from platform.common.config import PlatformSettings
from platform.common.llm.exceptions import RateLimitError
from platform.common.llm.mock_provider import MockLLMProvider
from platform.common.middleware.rate_limit_middleware import RateLimitMiddleware
from platform.common.rate_limiter.service import RateLimitEvaluation, ResolvedRateLimitPolicy
from platform.execution import scheduler as scheduler_module
from platform.execution.models import (
    ApprovalDecision,
    ApprovalTimeoutAction,
    ExecutionStatus,
)
from platform.execution.scheduler import PriorityScorer, SchedulerService
from platform.localization.tooling import drift_check
from platform.trust.repository import TrustRepository
from platform.workflows.ir import ApprovalConfigIR, RetryConfigIR, StepIR, WorkflowIR
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import Response
from starlette.requests import Request
from tests.unit.admin.test_workbench_services import _QueueSession, _Result


def _request(
    path: str = "/api/v1/workspaces",
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    user: dict[str, Any] | None = None,
    client: tuple[str, int] | None = ("198.51.100.9", 12345),
) -> Request:
    app = FastAPI()
    app.state.settings = PlatformSettings()
    app.state.clients = {"redis": object()}
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": headers or [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": client,
            "app": app,
        }
    )
    if user is not None:
        request.state.user = user
    return request


def test_rate_limit_middleware_static_helpers_cover_principal_and_header_edges() -> None:
    middleware = RateLimitMiddleware(FastAPI())

    assert middleware._source_ip(_request(headers=[(b"x-forwarded-for", b"10.0.0.1, 10.0.0.2")]))
    assert middleware._source_ip(_request()) == "198.51.100.9"
    assert middleware._source_ip(_request(client=None)) == "unknown"
    assert middleware._principal(
        _request(user={"principal_type": "service", "principal_id": "svc-1"})
    ) == ("service", "svc-1", False)
    assert middleware._principal(_request("/health")) == ("anon", "198.51.100.9", True)
    assert middleware._principal(_request("/api/v1/accounts/invitations/token")) == (
        "anon",
        "198.51.100.9",
        True,
    )
    assert middleware._settings(_request()).api_governance is not None
    assert middleware._redis(_request()) is not None

    evaluation = RateLimitEvaluation(
        policy=ResolvedRateLimitPolicy(
            principal_kind="user",
            principal_key="u1",
            tier_name="default",
            requests_per_minute=60,
            requests_per_hour=600,
            requests_per_day=6000,
        ),
        decision=MultiWindowRateLimitResult(
            allowed=True,
            remaining_minute=5,
            remaining_hour=4,
            remaining_day=3,
            retry_after_ms=0,
        ),
        reset_epoch_seconds=123,
    )
    response = Response()
    middleware._apply_headers(response, evaluation=evaluation, limit=60, remaining="3")

    assert middleware._remaining_value(evaluation) == 3
    assert response.headers["X-RateLimit-Reset"] == "123"


class _MockRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.sets: dict[str, set[str]] = {}
        self.keys: dict[str, str | bytes] = {}
        self.published: list[tuple[str, str]] = []
        self.commands: list[tuple[str, str, str]] = []

    async def sadd(self, key: str, value: str) -> None:
        self.sets.setdefault(key, set()).add(value)

    async def rpush(self, key: str, value: str) -> None:
        self.lists.setdefault(key, []).append(value)

    async def publish(self, channel: str, payload: str) -> None:
        self.published.append((channel, payload))

    async def execute_command(self, command: str, channel: str, payload: str) -> None:
        self.commands.append((command, channel, payload))

    async def llen(self, key: str) -> int:
        return len(self.lists.get(key, []))

    async def smembers(self, key: str) -> set[str]:
        return self.sets.get(key, set())

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.lists.pop(key, None)

    async def lrange(self, key: str, _start: int, _stop: int) -> list[str]:
        return self.lists.get(key, [])

    async def lpop(self, key: str) -> str | None:
        values = self.lists.get(key, [])
        return values.pop(0) if values else None

    async def ltrim(self, key: str, start: int, stop: int) -> None:
        self.lists[key] = self.lists.get(key, [])[start : stop + 1 if stop != -1 else None]

    async def get(self, key: str) -> str | bytes | None:
        return self.keys.get(key)

    async def set(
        self,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        ttl: int | None = None,
    ) -> None:
        if ex is not None:
            raise TypeError("ttl keyword required")
        self.keys[key] = value
        assert ttl is not None


class _RedisWrapper:
    def __init__(self, client: _MockRedis) -> None:
        self.client = client

    async def _get_client(self) -> _MockRedis:
        return self.client


@pytest.mark.asyncio
async def test_mock_llm_provider_queue_rate_limit_and_redis_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _MockRedis()
    provider = MockLLMProvider(_RedisWrapper(redis))

    with pytest.raises(KeyError):
        await provider.set_rate_limit_error("agent_response")
    monkeypatch.setenv("FEATURE_E2E_MODE", "true")
    with pytest.raises(ValueError, match="at least 1"):
        await provider.set_rate_limit_error("agent_response", count=0)

    await provider.set_response("agent_response", "queued", streaming_chunks=["a", "b"])
    await provider.set_responses({"judge_verdict": ["allow"]})
    assert (await provider.queue_depth())["agent_response"] == 1

    assert await provider.generate(
        "agent_response",
        "prompt",
        model="mock",
        temperature=0,
        max_tokens=10,
        correlation_context={"cid": "1"},
    ) == "queued"
    assert [
        chunk
        async for chunk in provider.stream(
            "missing",
            "prompt",
            model="mock",
            temperature=0,
            max_tokens=10,
        )
    ] == ["Mock response for missing"]

    calls = await provider.get_calls(pattern="agent_response", since="0000")
    assert calls[0].from_queue is True
    await provider.clear_queue("judge_verdict")
    await provider.clear_queue()

    await provider.set_rate_limit_error("agent_response", count=2)
    redis.keys[provider._rate_limit_key("agent_response")] = b"1"
    with pytest.raises(RateLimitError):
        await provider._raise_rate_limit_if_configured("agent_response")
    redis.keys[provider._rate_limit_key("agent_response")] = "0"
    await provider._raise_rate_limit_if_configured("agent_response")
    redis.keys.pop(provider._rate_limit_key("agent_response"))
    await provider._raise_rate_limit_if_configured("agent_response")

    no_publish = SimpleNamespace(execute_command=redis.execute_command)
    await provider._publish(no_publish, "channel", "payload")
    assert redis.commands == [("PUBLISH", "channel", "payload")]
    with pytest.raises(AttributeError):
        await provider._publish(object(), "channel", "payload")


def test_localization_drift_helpers_cover_path_and_threshold_edges(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages = tmp_path / "apps" / "web" / "messages"
    (messages / "en").mkdir(parents=True)
    (messages / "es").mkdir(parents=True)
    (messages / "fr").mkdir(parents=True)
    (messages / "en" / "admin.json").write_text('{"admin": {"title": "Admin"}}')
    (messages / "es" / "bad.json").write_text("{")
    (messages / "fr" / "list.json").write_text("[]")

    touched = drift_check.collect_touched_namespaces(
        [
            "apps/web/messages/en/admin.json",
            "apps/web/messages/es/bad.json",
            "apps/web/messages/fr/list.json",
            "apps/web/messages/en/missing.json",
            "apps/web/messages/en/readme.md",
        ],
        repo_root=tmp_path,
    )

    assert touched == {"admin", "bad", "list"}

    now = datetime(2026, 4, 29, tzinfo=UTC)
    response = drift_check.evaluate_drift(
        {
            "en": {
                "admin": now - timedelta(days=30),
                "fresh": now - timedelta(days=2),
            },
            "es": {"admin": now - timedelta(days=1)},
        },
        {"admin", "fresh", ""},
        threshold_days=7,
        locales=("en", "es", "fr"),
        now=now,
    )

    assert any(row.locale_code == "fr" and row.over_threshold for row in response.rows)
    assert any(row.locale_code == "es" and row.days_drift == 0 for row in response.rows)
    assert drift_check._calculate_days_drift(None, None, now) is None
    assert drift_check._calculate_days_drift(now, now, now) == 0.0

    completed = SimpleNamespace(stdout="apps/web/messages/en/admin.json\n\n")
    monkeypatch.setattr(drift_check.subprocess, "run", lambda *_args, **_kwargs: completed)
    assert drift_check.get_changed_message_paths("main", repo_root=tmp_path) == [
        "apps/web/messages/en/admin.json"
    ]

    drift_check.emit_result(response)
    ok = drift_check.evaluate_drift({"en": {"fresh": now}}, {"fresh"}, locales=("en",), now=now)
    drift_check.emit_result(ok)


@pytest.mark.asyncio
async def test_localization_async_main_returns_status(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 4, 29, tzinfo=UTC)
    failing = drift_check.evaluate_drift(
        {"en": {"admin": now - timedelta(days=30)}},
        {"admin"},
        threshold_days=1,
        locales=("en", "es"),
        now=now,
    )
    passing = drift_check.evaluate_drift(
        {"en": {"admin": now}},
        {"admin"},
        threshold_days=1,
        locales=("en",),
        now=now,
    )

    async def fail_check(**_kwargs: Any):
        return failing

    async def pass_check(**_kwargs: Any):
        return passing

    monkeypatch.setattr(drift_check, "run_drift_check", fail_check)
    assert await drift_check.async_main(["--pr-base", "main"]) == 1
    monkeypatch.setattr(drift_check, "run_drift_check", pass_check)
    assert await drift_check.async_main(["--pr-base", "main"]) == 0


@pytest.mark.asyncio
async def test_admin_security_scheduler_scan_and_missing_scheduler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Session:
        async def commit(self) -> None:
            return None

    class Factory:
        def __call__(self) -> Factory:
            return self

        async def __aenter__(self) -> Session:
            return Session()

        async def __aexit__(self, *_args: Any) -> None:
            return None

    class TwoPerson:
        def __init__(self, *_args: Any) -> None:
            return None

        async def expire_requests(self) -> int:
            return 2

    class Impersonation:
        def __init__(self, *_args: Any) -> None:
            return None

        async def expire_sessions(self) -> int:
            return 3

    app = SimpleNamespace(
        state=SimpleNamespace(
            settings=PlatformSettings(),
            clients={"redis": object(), "kafka": None},
        )
    )
    monkeypatch.setattr(security_scheduler.database, "AsyncSessionLocal", Factory())
    monkeypatch.setattr(
        security_scheduler,
        "build_notifications_service",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(security_scheduler, "TwoPersonAuthService", TwoPerson)
    monkeypatch.setattr(security_scheduler, "ImpersonationService", Impersonation)

    assert await security_scheduler.run_admin_security_expiry_scan(app) == (2, 3)

    original_import = __import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "apscheduler.schedulers.asyncio":
            raise ImportError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    assert security_scheduler.build_admin_security_expiry_scheduler(app) is None


class _SchedulerRedisClient:
    def __init__(self, client: Any) -> None:
        self.client = client

    async def _get_client(self) -> Any:
        return self.client


class _SchedulerRedis:
    def __init__(self) -> None:
        self.values: dict[str, bool] = {}
        self.deleted: list[str] = []

    async def set(self, key: str, _value: str, *, ex: int, nx: bool) -> bool:
        assert ex == 300
        assert nx is True
        return self.values.get(key, True)

    async def exists(self, key: str) -> bool:
        return self.values.get(key, False)

    async def delete(self, key: str) -> None:
        self.deleted.append(key)


class _SchedulerRepository:
    def __init__(self) -> None:
        self.session = object()
        self.leases: dict[str, Any] = {}
        self.created_leases: list[Any] = []
        self.released: list[tuple[Any, bool]] = []
        self.statuses: list[tuple[Any, ExecutionStatus, dict[str, Any]]] = []
        self.waits: dict[tuple[Any, str], Any] = {}
        self.created_waits: list[Any] = []
        self.updated_waits: list[tuple[Any, dict[str, Any]]] = []
        self.pending_waits: list[Any] = []
        self.executions: dict[Any, Any] = {}
        self.task_plan_records: list[Any] = []

    async def create_dispatch_lease(self, lease: Any) -> None:
        self.created_leases.append(lease)

    async def get_active_dispatch_lease(self, _execution_id: Any, step_id: str) -> Any:
        return self.leases.get(step_id)

    async def release_dispatch_lease(
        self,
        lease: Any,
        *,
        released_at: datetime,
        expired: bool,
    ) -> None:
        assert released_at.tzinfo is not None
        self.released.append((lease, expired))

    async def update_execution_status(
        self,
        execution: Any,
        status: ExecutionStatus,
        **kwargs: Any,
    ) -> None:
        self.statuses.append((execution, status, kwargs))
        execution.status = status
        for key, value in kwargs.items():
            setattr(execution, key, value)

    async def get_approval_wait(self, execution_id: Any, step_id: str) -> Any:
        return self.waits.get((execution_id, step_id))

    async def create_approval_wait(self, approval_wait: Any) -> None:
        self.created_waits.append(approval_wait)
        self.waits[(approval_wait.execution_id, approval_wait.step_id)] = approval_wait

    async def list_pending_approval_waits(self, _now: datetime) -> list[Any]:
        return self.pending_waits

    async def update_approval_wait(self, approval_wait: Any, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(approval_wait, key, value)
        self.updated_waits.append((approval_wait, kwargs))

    async def get_execution_by_id(self, execution_id: Any) -> Any:
        return self.executions.get(execution_id)

    async def upsert_task_plan_record(self, record: Any) -> None:
        self.task_plan_records.append(record)


def _scheduler(
    *,
    repository: _SchedulerRepository | None = None,
    redis: _SchedulerRedis | None = None,
    execution_service: Any | None = None,
    object_storage: Any | None = None,
    runtime_controller: Any | None = None,
    context_engineering_service: Any | None = None,
    interactions_service: Any | None = None,
    checkpoint_service: Any | None = None,
    settings: Any | None = None,
) -> SchedulerService:
    return SchedulerService(
        repository=repository or _SchedulerRepository(),
        execution_service=execution_service or SimpleNamespace(),
        projector=SimpleNamespace(),
        settings=settings or SimpleNamespace(feature_e2e_mode=False),
        producer=None,
        redis_client=_SchedulerRedisClient(redis or _SchedulerRedis()),
        object_storage=object_storage or SimpleNamespace(),
        runtime_controller=runtime_controller or SimpleNamespace(),
        reasoning_engine=SimpleNamespace(),
        context_engineering_service=context_engineering_service,
        interactions_service=interactions_service,
        checkpoint_service=checkpoint_service,
    )


def _execution(**overrides: Any) -> SimpleNamespace:
    base = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "workflow_version_id": uuid4(),
        "workflow_definition_id": uuid4(),
        "workflow_version": 3,
        "created_at": datetime.now(UTC),
        "sla_deadline": datetime.now(UTC) + timedelta(minutes=5),
        "status": SimpleNamespace(value="running"),
        "contract_snapshot": {
            "model_binding": {"provider": "mock"},
            "source_policy_ids": [uuid4(), None],
            "agent_revision": "rev-1",
        },
        "correlation_workspace_id": None,
        "correlation_conversation_id": uuid4(),
        "correlation_interaction_id": uuid4(),
        "correlation_fleet_id": uuid4(),
        "correlation_goal_id": uuid4(),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_scheduler_runtime_contract_budget_and_task_plan_edges() -> None:
    scheduler = _scheduler()
    execution = _execution()
    step = StepIR(
        step_id="step-a",
        step_type="agent_task",
        agent_fqn="agent.demo",
        tool_fqn="tool.demo",
        input_bindings={"from_step": "$.steps.previous.output", "literal": "hello"},
        reasoning_mode="deep",
        compute_budget=0.4,
        context_budget_tokens=200,
    )
    ir = WorkflowIR(
        schema_version=1,
        workflow_id="wf",
        steps=[
            StepIR(step_id="start", step_type="tool_task"),
            step,
            StepIR(step_id="done", step_type="approval_gate", retry_config=RetryConfigIR()),
        ],
        dag_edges=[("start", "step-a"), ("step-a", "done")],
        metadata={"compute_budget": 0.8},
    )
    state = SimpleNamespace(
        completed_step_ids=["start"],
        active_step_ids=[],
        step_results={},
    )

    payload = scheduler._runtime_contract_payload(
        execution,
        step,
        {"context_engineering_profile_id": uuid4(), "created_at": datetime.now(UTC)},
        compute_budget=0.4,
        effective_budget_scope="step",
    )
    fallback_revision = scheduler._runtime_agent_revision(
        _execution(contract_snapshot={}),
        StepIR(step_id="fallback", step_type="tool_task", tool_fqn="tool.only"),
    )
    budget, scope = scheduler._resolve_effective_compute_budget(ir, step)
    workflow_budget, workflow_scope = scheduler._resolve_effective_compute_budget(
        WorkflowIR(1, "wf", [step], [], metadata={"compute_budget": 0.2}),
        StepIR(step_id="s", step_type="agent_task", compute_budget=2.0),
    )
    no_budget = scheduler._resolve_effective_compute_budget(
        WorkflowIR(1, "wf", [step], [], metadata={"compute_budget": False}),
        StepIR(step_id="s", step_type="agent_task", compute_budget=None),
    )
    step_only_budget = scheduler._resolve_effective_compute_budget(
        WorkflowIR(1, "wf", [step], [], metadata={}),
        StepIR(step_id="s", step_type="agent_task", compute_budget=0.3),
    )
    string_model_binding = scheduler._runtime_contract_payload(
        _execution(contract_snapshot={"model_binding": '{"provider":"mock"}'}),
        step,
        {},
        compute_budget=None,
        effective_budget_scope=None,
    )
    blank_model_binding = scheduler._runtime_contract_payload(
        _execution(contract_snapshot={"model_binding": "  ", "policy_ids": [uuid4()]}),
        StepIR(step_id="blank", step_type="tool_task"),
        {},
        compute_budget=None,
        effective_budget_scope=None,
    )

    assert json.loads(payload["model_binding"]) == {"provider": "mock"}
    assert string_model_binding["model_binding"] == '{"provider":"mock"}'
    assert blank_model_binding["model_binding"] == '"  "'
    assert blank_model_binding["policy_ids"]
    assert payload["env_vars"]["AGENT_FQN"] == "agent.demo"
    assert payload["env_vars"]["TOOL_FQN"] == "tool.demo"
    assert "reasoning_budget_envelope_json" in payload
    assert fallback_revision == "tool.only"
    assert (budget, scope) == (0.4, "step")
    assert (workflow_budget, workflow_scope) == (0.2, "workflow")
    assert no_budget == (None, None)
    assert step_only_budget == (0.3, "step")
    assert SchedulerService._is_valid_compute_budget(True) is False
    assert SchedulerService._runtime_json_default(datetime(2026, 1, 1, tzinfo=UTC)).startswith(
        "2026-01-01"
    )
    assert [item.step_id for item in SchedulerService._runnable_steps(ir, state)] == ["step-a"]
    assert SchedulerService._dependency_depths(ir) == {"start": 0.0, "step-a": 1.0, "done": 2.0}
    assert (
        PriorityScorer().compute(
            StepIR(
                step_id="approval",
                step_type="approval_gate",
                retry_config=RetryConfigIR(),
                context_budget_tokens=10,
            ),
            {
                "now": datetime.now(UTC),
                "execution": _execution(status=SimpleNamespace(value="failed")),
                "dependency_depth": {"approval": 2},
            },
        )
        > 0
    )

    plan = await scheduler._build_task_plan_payload(execution, step)
    assert plan["parameters"]["from_step"]["provenance"] == "prev_step_output"
    assert plan["parameters"]["literal"]["provenance"] == "user_input"

    context_scheduler = _scheduler(
        context_engineering_service=SimpleNamespace(
            get_plan_context=lambda **_kwargs: {"from_context": True}
        )
    )
    assert await context_scheduler._build_task_plan_payload(execution, step) == {
        "from_context": True
    }


@pytest.mark.asyncio
async def test_scheduler_lease_retry_and_runtime_dispatch_edges() -> None:
    repository = _SchedulerRepository()
    redis = _SchedulerRedis()
    scheduler = _scheduler(repository=repository, redis=redis)
    execution = _execution()
    active_step = StepIR(step_id="active", step_type="agent_task")
    expired_step = StepIR(step_id="expired", step_type="agent_task")
    ir = WorkflowIR(1, "wf", [active_step, expired_step], [])

    assert await scheduler._acquire_lease(execution.id, "new") is True
    redis.values[f"exec:lease:{execution.id}:blocked"] = False
    assert await scheduler._acquire_lease(execution.id, "blocked") is False

    valid_lease = SimpleNamespace(expires_at=datetime.now(UTC) + timedelta(minutes=1))
    expired_lease = SimpleNamespace(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    repository.leases = {"active": valid_lease, "expired": expired_lease}
    redis.values[f"exec:lease:{execution.id}:active"] = True
    retryable = await scheduler._collect_retryable_steps(
        execution,
        ir,
        SimpleNamespace(active_step_ids=["missing", "active", "expired"]),
    )
    no_active_retryable = await scheduler._collect_retryable_steps(
        execution,
        ir,
        SimpleNamespace(active_step_ids=[]),
    )

    assert [step.step_id for step in retryable] == ["expired"]
    assert no_active_retryable == []
    assert repository.released[-1] == (expired_lease, True)

    await scheduler._release_step_dispatch_lease(execution.id, "expired")
    assert f"exec:lease:{execution.id}:expired" in redis.deleted
    no_delete_scheduler = _scheduler(redis=SimpleNamespace())
    await no_delete_scheduler._release_step_dispatch_lease(execution.id, "missing")

    class Runtime:
        def __init__(self) -> None:
            self.launches = 0
            self.dispatches: list[dict[str, Any]] = []

        def launch_runtime(self, *_args: Any, **_kwargs: Any) -> None:
            self.launches += 1
            raise RuntimeError("fall back")

        async def dispatch(self, payload: dict[str, Any]) -> None:
            self.dispatches.append(payload)

    runtime = Runtime()
    scheduler = _scheduler(runtime_controller=runtime)
    await scheduler._dispatch_to_runtime(
        execution,
        WorkflowIR(1, "wf", [active_step], [], metadata={"compute_budget": 0.5}),
        active_step,
        task_plan_payload={"ready": True},
    )

    assert runtime.launches == 1
    assert runtime.dispatches[0]["step_id"] == "active"
    assert scheduler._e2e_runtime_simulation_enabled() is False

    class StubRuntime:
        def __init__(self) -> None:
            self.payloads: list[dict[str, Any]] = []
            self.stub = SimpleNamespace(dispatch=self.dispatch)

        async def dispatch(self, payload: dict[str, Any]) -> None:
            self.payloads.append(payload)

    stub_runtime = StubRuntime()
    await _scheduler(runtime_controller=stub_runtime)._dispatch_to_runtime(
        execution,
        WorkflowIR(1, "wf", [active_step], []),
        active_step,
        task_plan_payload={"ready": True},
    )
    assert stub_runtime.payloads[0]["step_id"] == "active"

    class AsyncLaunchRuntime:
        def __init__(self) -> None:
            self.launched = 0

        async def launch_runtime(self, *_args: Any, **_kwargs: Any) -> None:
            self.launched += 1

    launch_runtime = AsyncLaunchRuntime()
    await _scheduler(runtime_controller=launch_runtime)._dispatch_to_runtime(
        execution,
        WorkflowIR(1, "wf", [active_step], []),
        active_step,
        task_plan_payload={"ready": True},
    )
    assert launch_runtime.launched == 1

    class LaunchOnlyRuntime:
        def launch_runtime(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("no fallback")

    with pytest.raises(RuntimeError, match="no fallback"):
        await _scheduler(runtime_controller=LaunchOnlyRuntime())._dispatch_to_runtime(
            execution,
            WorkflowIR(1, "wf", [active_step], []),
            active_step,
            task_plan_payload={"ready": True},
        )


@pytest.mark.asyncio
async def test_scheduler_checkpoint_approval_and_task_plan_edges() -> None:
    class ExecutionEvents:
        task_plan_bucket = "task-plans"

        def __init__(self) -> None:
            self.events: list[dict[str, Any]] = []

        async def record_runtime_event(self, execution_id: Any, **kwargs: Any) -> None:
            self.events.append({"execution_id": execution_id, **kwargs})

    class Storage:
        def __init__(self, *, fail: bool = False) -> None:
            self.fail = fail
            self.buckets: list[str] = []
            self.uploads: list[tuple[str, str, bytes, str]] = []

        async def create_bucket_if_not_exists(self, bucket: str) -> None:
            self.buckets.append(bucket)
            if self.fail:
                raise RuntimeError("bucket unavailable")

        async def upload_object(
            self,
            bucket: str,
            key: str,
            payload: bytes,
            *,
            content_type: str,
        ) -> None:
            self.uploads.append((bucket, key, payload, content_type))

    class Checkpoint:
        def __init__(self, *, should_capture: bool = True, fail: bool = False) -> None:
            self.should_capture_result = should_capture
            self.fail = fail
            self.captures: list[dict[str, Any]] = []

        def should_capture(self, step: StepIR, policy: dict[str, Any]) -> bool:
            self.captures.append({"step": step.step_id, "policy": policy, "checked": True})
            return self.should_capture_result

        async def capture(self, **kwargs: Any) -> None:
            self.captures.append(kwargs)
            if self.fail:
                raise RuntimeError("checkpoint store down")

    class Interactions:
        def __init__(self) -> None:
            self.requests: list[dict[str, Any]] = []

        async def create_approval_request(self, **kwargs: Any) -> None:
            self.requests.append(kwargs)

    step = StepIR(
        step_id="review",
        step_type="approval_gate",
        approval_config=ApprovalConfigIR(
            required_approvers=["ops@example.com"],
            timeout_seconds=30,
            timeout_action="skip",
        ),
    )
    execution = _execution(checkpoint_policy_snapshot={"before_dispatch": True})
    state = SimpleNamespace(step_results={}, completed_step_ids=[], active_step_ids=[])
    events = ExecutionEvents()

    await _scheduler(repository=_SchedulerRepository()).handle_reprioritization_trigger(
        "manual",
        uuid4(),
    )
    assert await _scheduler()._capture_pre_dispatch_checkpoint(execution, step, state) is True

    skipped_checkpoint = Checkpoint(should_capture=False)
    skip_scheduler = _scheduler(checkpoint_service=skipped_checkpoint)
    assert await skip_scheduler._capture_pre_dispatch_checkpoint(execution, step, state) is True
    assert len(skipped_checkpoint.captures) == 1

    failing_repository = _SchedulerRepository()
    failing_checkpoint = Checkpoint(fail=True)
    failing_scheduler = _scheduler(
        repository=failing_repository,
        execution_service=events,
        checkpoint_service=failing_checkpoint,
    )

    assert (
        await failing_scheduler._capture_pre_dispatch_checkpoint(execution, step, state)
        is False
    )
    assert failing_repository.statuses[-1][1] == ExecutionStatus.paused
    assert events.events[-1]["event_type"].value == "failed"

    existing_wait_repository = _SchedulerRepository()
    existing_wait_repository.waits[(execution.id, "review")] = object()
    await _scheduler(repository=existing_wait_repository)._handle_approval_gate(execution, step)
    assert existing_wait_repository.created_waits == []

    no_config_repository = _SchedulerRepository()
    await _scheduler(repository=no_config_repository)._handle_approval_gate(
        execution,
        StepIR(step_id="plain", step_type="approval_gate"),
    )
    assert no_config_repository.created_waits == []

    approval_repository = _SchedulerRepository()
    interactions = Interactions()
    approval_scheduler = _scheduler(
        repository=approval_repository,
        execution_service=events,
        interactions_service=interactions,
    )
    await approval_scheduler._handle_approval_gate(execution, step)

    created_wait = approval_repository.created_waits[0]
    assert created_wait.required_approvers == ["ops@example.com"]
    assert created_wait.timeout_action == ApprovalTimeoutAction.skip
    assert approval_repository.statuses[-1][1] == ExecutionStatus.waiting_for_approval
    assert interactions.requests[0]["step_id"] == "review"

    fail_execution = _execution()
    skip_execution = _execution()
    missing_wait = SimpleNamespace(
        execution_id=uuid4(),
        step_id="missing",
        timeout_action=ApprovalTimeoutAction.escalate,
    )
    fail_wait = SimpleNamespace(
        execution_id=fail_execution.id,
        step_id="fail",
        timeout_action=ApprovalTimeoutAction.fail,
    )
    skip_wait = SimpleNamespace(
        execution_id=skip_execution.id,
        step_id="skip",
        timeout_action=ApprovalTimeoutAction.skip,
    )
    approval_repository.pending_waits = [skip_wait, fail_wait, missing_wait]
    approval_repository.executions = {
        fail_execution.id: fail_execution,
        skip_execution.id: skip_execution,
    }
    await approval_scheduler.scan_approval_timeouts()

    assert skip_wait.decision == ApprovalDecision.approved
    assert fail_wait.decision == ApprovalDecision.timed_out
    assert approval_repository.statuses[-2][1] == ExecutionStatus.running
    assert approval_repository.statuses[-1][1] == ExecutionStatus.failed

    plan_repository = _SchedulerRepository()
    storage = Storage()
    plan_scheduler = _scheduler(
        repository=plan_repository,
        execution_service=events,
        object_storage=storage,
    )
    task_step = StepIR(
        step_id="task",
        step_type="agent_task",
        agent_fqn="agent.demo",
        tool_fqn="tool.demo",
        input_bindings={"source": "$.steps.start.output", "literal": "value"},
    )
    payload = await plan_scheduler._persist_task_plan(execution, task_step)

    assert payload["selected_agent_fqn"] == "agent.demo"
    assert storage.buckets == ["task-plans"]
    assert storage.uploads[0][3] == "application/json"
    assert plan_repository.task_plan_records[0].considered_agents_count == 1
    assert plan_repository.task_plan_records[0].parameter_sources == [
        "prev_step_output",
        "user_input",
    ]

    failed_storage_repository = _SchedulerRepository()
    failed_storage_scheduler = _scheduler(
        repository=failed_storage_repository,
        execution_service=events,
        object_storage=Storage(fail=True),
    )
    failed_payload = await failed_storage_scheduler._persist_task_plan(execution, task_step)

    assert failed_payload["step_id"] == "task"
    assert failed_storage_repository.task_plan_records[0].storage_key.endswith(
        "/task/task-plan.json"
    )


@pytest.mark.asyncio
async def test_scheduler_e2e_publish_and_message_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Producer:
        def __init__(self) -> None:
            self.published: list[dict[str, Any]] = []

        async def publish(self, **kwargs: Any) -> None:
            self.published.append(kwargs)

    class InteractionRepository:
        def __init__(self) -> None:
            self.interaction: Any | None = None
            self.latest: Any | None = None
            self.incremented: Any | None = object()
            self.created: list[dict[str, Any]] = []

        async def get_interaction(self, _interaction_id: Any, _workspace_id: Any) -> Any:
            return self.interaction

        async def get_latest_agent_message(self, _interaction_id: Any) -> Any:
            return self.latest

        async def increment_message_count(self, **_kwargs: Any) -> Any:
            return self.incremented

        async def create_message(self, **kwargs: Any) -> Any:
            self.created.append(kwargs)
            return SimpleNamespace(
                id=uuid4(),
                sender_identity=kwargs["sender_identity"],
                message_type=kwargs["message_type"],
            )

    class BrokenMockProvider:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        async def generate(self, *_args: Any, **_kwargs: Any) -> str:
            raise RuntimeError("mock queue unavailable")

    published_messages: list[Any] = []

    async def publish_message_received(*args: Any) -> None:
        published_messages.append(args)

    interaction_repository = InteractionRepository()
    monkeypatch.setattr(
        scheduler_module,
        "InteractionsRepository",
        lambda _session: interaction_repository,
    )
    monkeypatch.setattr(
        scheduler_module,
        "publish_message_received",
        publish_message_received,
    )
    monkeypatch.setattr(scheduler_module, "MockLLMProvider", BrokenMockProvider)

    repository = _SchedulerRepository()
    producer = Producer()
    scheduler = _scheduler(
        repository=repository,
        settings=SimpleNamespace(
            feature_e2e_mode=True,
            interactions=SimpleNamespace(max_messages_per_conversation=7),
        ),
    )
    scheduler.producer = producer
    execution = _execution()
    step = StepIR(step_id="e2e", step_type="agent_task", agent_fqn="agent.demo")

    assert (
        await scheduler._generate_e2e_agent_response(execution, step, {"task": True})
        == "E2E runtime completed step e2e."
    )

    await _scheduler()._publish_e2e_reasoning_event(execution, step, "unused.json")
    await scheduler._publish_e2e_reasoning_event(execution, step, "trace/key.json")
    assert producer.published[0]["topic"] == "runtime.reasoning"
    assert producer.published[0]["payload"]["storage_key"] == "trace/key.json"

    await scheduler._append_e2e_agent_message(
        _execution(correlation_interaction_id=None),
        step,
        "ignored",
    )
    assert interaction_repository.created == []

    interaction_repository.interaction = None
    await scheduler._append_e2e_agent_message(execution, step, "ignored")
    assert interaction_repository.created == []

    interaction = SimpleNamespace(
        id=uuid4(),
        conversation_id=execution.correlation_conversation_id,
        workspace_id=execution.workspace_id,
        goal_id=execution.correlation_goal_id,
    )
    interaction_repository.interaction = interaction
    interaction_repository.latest = SimpleNamespace(
        metadata_json={"execution_id": str(execution.id)}
    )
    await scheduler._append_e2e_agent_message(execution, step, "ignored")
    assert interaction_repository.created == []

    interaction_repository.latest = None
    interaction_repository.incremented = None
    await scheduler._append_e2e_agent_message(execution, step, "ignored")
    assert interaction_repository.created == []

    interaction_repository.incremented = object()
    await scheduler._append_e2e_agent_message(execution, step, "created")

    assert interaction_repository.created[0]["sender_identity"] == "agent.demo"
    assert interaction_repository.created[0]["metadata"]["source"] == "e2e_runtime_simulator"
    assert published_messages[0][1].message_id is not None


class _TrustSession(_QueueSession):
    def __init__(
        self,
        execute_results: list[_Result] | None = None,
        scalar_results: list[Any] | None = None,
    ) -> None:
        super().__init__(execute_results)
        self.scalar_results = scalar_results or []

    async def scalar(self, _statement: Any) -> Any:
        return self.scalar_results.pop(0) if self.scalar_results else None


@pytest.mark.asyncio
async def test_trust_repository_empty_and_optional_filter_edges() -> None:
    day = datetime(2026, 4, 29, tzinfo=UTC)

    none_repository = TrustRepository(_TrustSession())
    assert await none_repository.update_moderation_policy(uuid4(), {"name": "missing"}) is None
    assert await none_repository.deactivate_moderation_policy(uuid4()) is None
    assert TrustRepository._moderation_event_filters({}) == []

    create_session = _TrustSession([_Result(scalar=None)])
    create_repository = TrustRepository(create_session)
    inactive_policy = SimpleNamespace(active=False, workspace_id=uuid4(), version=1)
    active_policy = SimpleNamespace(active=True, workspace_id=uuid4(), version=1)
    assert await create_repository.create_moderation_policy(inactive_policy) is inactive_policy
    assert await create_repository.create_moderation_policy(active_policy) is active_policy
    assert active_policy.version == 1

    aggregate_repository = TrustRepository(
        _TrustSession([_Result(mappings=[{"action": "block", "count": 3}])])
    )
    assert await aggregate_repository.aggregate_moderation_events(
        {"limit": 5},
        ["action"],
    ) == [{"action": "block", "count": 3}]

    revision = object()
    profile = object()
    revision_repository = TrustRepository(
        _TrustSession([_Result(rows=[]), _Result(rows=[(revision, profile)])])
    )
    assert await revision_repository.get_agent_revision_with_profile(uuid4()) is None
    assert await revision_repository.get_agent_revision_with_profile(uuid4()) == (
        revision,
        profile,
    )

    template = SimpleNamespace(is_published=False)
    template_repository = TrustRepository(_TrustSession([_Result(scalars=[template])]))
    assert await template_repository.list_contract_templates(include_unpublished=True) == [
        template
    ]

    signal = SimpleNamespace(id=uuid4())
    signal_repository = TrustRepository(
        _TrustSession([_Result(scalars=[signal])], scalar_results=[2])
    )
    signals, total = await signal_repository.list_trust_signals_for_agent(
        "agent",
        since=day - timedelta(hours=1),
        signal_type="quality",
    )
    assert signals == [signal]
    assert total == 2

    fleet_config = SimpleNamespace(id=uuid4())
    global_config = SimpleNamespace(id=uuid4())
    guardrail_repository = TrustRepository(
        _TrustSession(
            [
                _Result(scalar=fleet_config),
                _Result(scalar=None),
                _Result(scalar=global_config),
            ]
        )
    )
    assert await guardrail_repository.get_guardrail_config("workspace", fleet_id="fleet") is (
        fleet_config
    )
    assert await guardrail_repository.get_guardrail_config("workspace", fleet_id="fallback") is (
        global_config
    )

    certification = SimpleNamespace(id=uuid4())
    breach_event = SimpleNamespace(id=uuid4())
    request = SimpleNamespace(id=uuid4())
    default_guardrail = SimpleNamespace(id=uuid4())
    optional_repository = TrustRepository(
        _TrustSession(
            [
                _Result(scalars=[certification]),
                _Result(scalars=[breach_event]),
                _Result(scalars=[request]),
                _Result(scalar=default_guardrail),
            ],
            scalar_results=[4],
        )
    )
    assert await optional_repository.list_certifications_for_agent("agent") == [certification]
    assert await optional_repository.list_breach_events(
        uuid4(),
        target_type="execution",
        start=day - timedelta(hours=1),
        end=day + timedelta(hours=1),
    ) == ([breach_event], 4)
    assert await optional_repository.list_recertification_requests(
        certification_id=uuid4(),
        status="pending",
    ) == [request]
    assert await optional_repository.get_guardrail_config("workspace") is default_guardrail


@pytest.mark.asyncio
async def test_trust_repository_crud_and_filter_edges() -> None:
    workspace_id = uuid4()
    policy_id = uuid4()
    current_policy = SimpleNamespace(active=True, version=4, workspace_id=workspace_id)
    new_policy = SimpleNamespace(active=True, version=1, workspace_id=workspace_id)
    existing_policy = SimpleNamespace(active=True, name="old")
    moderation_event = SimpleNamespace(id=uuid4())
    certification = SimpleNamespace(id=uuid4())
    certifier = SimpleNamespace(id=uuid4(), is_active=True)
    contract = SimpleNamespace(id=uuid4(), is_archived=False)
    day = datetime(2026, 4, 29, tzinfo=UTC)
    session = _TrustSession(
        [
            _Result(scalar=current_policy),
            _Result(scalars=[current_policy]),
            _Result(scalars=[moderation_event]),
            _Result(mappings=[{"category": "safety", "agent": "agent", "day": day, "count": 2}]),
            _Result(scalar=certification),
            _Result(scalars=[certification]),
            _Result(scalars=[certification]),
            _Result(scalars=[certification]),
            _Result(scalar=certifier),
            _Result(scalars=[certifier]),
            _Result(scalar=certifier),
            _Result(scalar=contract),
            _Result(scalars=[contract]),
            _Result(scalar=contract),
            _Result(scalar=contract),
            _Result(scalars=[SimpleNamespace(is_published=True)]),
            _Result(scalar=SimpleNamespace(id=uuid4())),
        ],
        scalar_results=[7, 1],
    )
    session.get_rows[policy_id] = existing_policy
    session.get_rows[moderation_event.id] = moderation_event
    repository = TrustRepository(session)

    created = await repository.create_moderation_policy(new_policy)  # type: ignore[arg-type]
    versions = await repository.list_moderation_policy_versions(workspace_id)
    updated = await repository.update_moderation_policy(policy_id, {"name": "new"})
    deactivated = await repository.deactivate_moderation_policy(policy_id)
    inserted_event = await repository.insert_moderation_event(moderation_event)  # type: ignore[arg-type]
    fetched_event = await repository.get_moderation_event(moderation_event.id)
    events, total = await repository.list_moderation_events(
        {
            "workspace_id": workspace_id,
            "agent_id": "agent",
            "action": "block",
            "since": day - timedelta(days=1),
            "until": day + timedelta(days=1),
            "limit": 10,
        }
    )
    aggregate = await repository.aggregate_moderation_events(
        {"workspace_id": workspace_id},
        ["category", "agent", "day"],
    )
    created_certification = await repository.create_certification(certification)  # type: ignore[arg-type]
    fetched_certification = await repository.get_certification(certification.id)
    assert await repository.list_certifications_for_agent("agent", allowed_ids=set()) == []
    allowed = await repository.list_certifications_for_agent(
        "agent",
        allowed_ids={certification.id},
    )
    active = await repository.list_active_certifications_for_agent("agent")
    stale = await repository.list_stale_certifications(day)
    created_certifier = await repository.create_certifier(certifier)  # type: ignore[arg-type]
    fetched_certifier = await repository.get_certifier(certifier.id)
    listed_certifiers = await repository.list_certifiers(include_inactive=False)
    deactivated_certifier = await repository.deactivate_certifier(certifier.id)
    created_contract = await repository.create_contract(contract)  # type: ignore[arg-type]
    fetched_contract = await repository.get_contract(contract.id)
    listed_contracts = await repository.list_contracts(workspace_id, agent_id="agent")
    updated_contract = await repository.update_contract(contract.id, {"name": "contract"})
    archived_contract = await repository.archive_contract(contract.id)
    templates = await repository.list_contract_templates(include_unpublished=False)
    template = await repository.get_contract_template(uuid4())
    has_inflight = await repository.has_inflight_execution_for_contract(contract.id)

    assert created.version == 5
    assert current_policy.active is False
    assert versions == [current_policy]
    assert updated.name == "new"
    assert deactivated.active is False
    assert inserted_event is moderation_event
    assert fetched_event is moderation_event
    assert events == [moderation_event]
    assert total == 7
    assert aggregate == [{"category": "safety", "agent": "agent", "day": "2026-04-29", "count": 2}]
    assert created_certification is certification
    assert fetched_certification is certification
    assert allowed == [certification]
    assert active == [certification]
    assert stale == [certification]
    assert created_certifier is certifier
    assert fetched_certifier is certifier
    assert listed_certifiers == [certifier]
    assert deactivated_certifier.is_active is False
    assert created_contract is contract
    assert fetched_contract is contract
    assert listed_contracts == [contract]
    assert updated_contract.name == "contract"
    assert archived_contract.is_archived is True
    assert templates[0].is_published is True
    assert template is not None
    assert has_inflight is True
    assert len(session.added) >= 4
    assert session.flushes >= 7
