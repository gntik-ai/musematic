from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.common.debug_logging.capture import DebugCaptureMiddleware
from platform.common.debug_logging.events import (
    DebugLoggingSessionExpiredPayload,
    publish_debug_logging_event,
)
from platform.common.debug_logging.models import (
    DebugLoggingCapture,
    DebugLoggingSession,
    DebugLoggingTerminationReason,
)
from platform.common.debug_logging.repository import DebugLoggingRepository, _apply_cursor, _page
from platform.common.debug_logging.router import (
    DebugLoggingMethodNotAllowedError,
    _actor_id,
    _correlation_id,
    _is_superadmin,
    _require_read_access,
    _require_write_access,
    _role_names,
    get_debug_logging_service,
    get_debug_logging_session,
    list_debug_logging_captures,
    list_debug_logging_sessions,
    open_debug_logging_session,
    patch_debug_logging_session,
    terminate_debug_logging_session,
)
from platform.common.debug_logging.schemas import DebugLoggingSessionCreateRequest
from platform.common.debug_logging.service import (
    DEBUG_SESSION_CACHE_CONTEXT,
    DEBUG_SESSION_SENTINEL,
    DebugLoggingConflictError,
    DebugLoggingService,
    purge_debug_captures,
)
from platform.common.exceptions import AuthorizationError, ValidationError
from types import SimpleNamespace, TracebackType
from uuid import UUID, uuid4

import pytest
from starlette.requests import Request


class FakeRedis:
    def __init__(self) -> None:
        self.cache: dict[tuple[str, str], dict[str, str]] = {}
        self.deleted: list[tuple[str, str]] = []
        self.set_calls: list[tuple[str, str, dict[str, str], int]] = []

    async def cache_get(self, context: str, key: str) -> dict[str, str] | None:
        return self.cache.get((context, key))

    async def cache_set(
        self,
        context: str,
        key: str,
        value: dict[str, str],
        *,
        ttl_seconds: int,
    ) -> None:
        self.cache[(context, key)] = value
        self.set_calls.append((context, key, value, ttl_seconds))

    async def cache_delete(self, context: str, key: str) -> None:
        self.deleted.append((context, key))
        self.cache.pop((context, key), None)


class FakeProducer:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object], UUID]] = []

    async def publish(
        self,
        topic: str,
        key: str,
        event_type: str,
        payload: dict[str, object],
        correlation_ctx,
        source: str,
    ) -> None:
        del topic, key, source
        self.events.append((event_type, payload, correlation_ctx.correlation_id))


class FakeRepository:
    def __init__(self) -> None:
        self.sessions: dict[UUID, DebugLoggingSession] = {}
        self.active_by_target: dict[tuple[str, UUID], DebugLoggingSession | None] = {}
        self.captures: list[DebugLoggingCapture] = []
        self.incremented: list[UUID] = []
        self.purge_cutoffs: list[datetime] = []

    async def create_session(self, debug_session: DebugLoggingSession) -> DebugLoggingSession:
        debug_session.id = uuid4()
        self.sessions[debug_session.id] = debug_session
        self.active_by_target[(debug_session.target_type, debug_session.target_id)] = debug_session
        return debug_session

    async def get_session(self, session_id: UUID) -> DebugLoggingSession | None:
        return self.sessions.get(session_id)

    async def find_active_session_for_target(
        self,
        target_type: str,
        target_id: UUID,
        *,
        now: datetime | None = None,
    ) -> DebugLoggingSession | None:
        del now
        return self.active_by_target.get((target_type, target_id))

    async def list_sessions(self, **kwargs) -> tuple[list[DebugLoggingSession], str | None]:
        del kwargs
        return list(self.sessions.values()), None

    async def terminate_session(
        self,
        debug_session: DebugLoggingSession,
        *,
        terminated_at: datetime,
        termination_reason: str,
    ) -> DebugLoggingSession:
        debug_session.terminated_at = terminated_at
        debug_session.termination_reason = termination_reason
        return debug_session

    async def append_capture(self, capture: DebugLoggingCapture) -> DebugLoggingCapture:
        capture.id = uuid4()
        self.captures.append(capture)
        return capture

    async def increment_capture_count(self, session_id: UUID) -> None:
        self.incremented.append(session_id)
        self.sessions[session_id].capture_count += 1

    async def list_captures(
        self,
        session_id: UUID,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[DebugLoggingCapture], str | None]:
        del session_id, limit, cursor
        return self.captures, None

    async def purge_old_captures(self, cutoff: datetime) -> int:
        self.purge_cutoffs.append(cutoff)
        return 3


class FakeScalarResult:
    def __init__(self, items: list[object] | None = None, rowcount: int | None = None) -> None:
        self.items = list(items or [])
        self.rowcount = rowcount

    def scalar_one_or_none(self) -> object | None:
        return self.items[0] if self.items else None

    def scalars(self) -> FakeScalarResult:
        return self

    def all(self) -> list[object]:
        return self.items


class FakeSession:
    def __init__(self, results: list[FakeScalarResult] | None = None) -> None:
        self.results = list(results or [])
        self.added: list[object] = []
        self.executed: list[object] = []
        self.flush_count = 0
        self.refreshes: list[object] = []

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flush_count += 1

    async def refresh(self, item: object) -> None:
        self.refreshes.append(item)

    async def execute(self, statement: object) -> FakeScalarResult:
        self.executed.append(statement)
        return self.results.pop(0) if self.results else FakeScalarResult()


class FakeManagedSession:
    def __init__(self, repository: FakeRepository, *, fail_commit: bool = False) -> None:
        self.repository = repository
        self.fail_commit = fail_commit
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> FakeManagedSession:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback

    async def commit(self) -> None:
        if self.fail_commit:
            raise RuntimeError("commit failed")
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _session(
    *,
    target_type: str = "user",
    target_id: UUID | None = None,
    requested_by: UUID | None = None,
    expires_at: datetime | None = None,
    terminated_at: datetime | None = None,
) -> DebugLoggingSession:
    now = datetime.now(UTC)
    return DebugLoggingSession(
        id=uuid4(),
        target_type=target_type,
        target_id=target_id or uuid4(),
        requested_by=requested_by or uuid4(),
        justification="Investigating production issue",
        started_at=now - timedelta(minutes=5),
        expires_at=expires_at or now + timedelta(minutes=5),
        terminated_at=terminated_at,
        termination_reason=None,
        capture_count=0,
        correlation_id=uuid4(),
    )


def _service(
    *,
    repository: FakeRepository | None = None,
    redis_client: FakeRedis | None = None,
    producer: FakeProducer | None = None,
) -> tuple[DebugLoggingService, FakeRepository, FakeRedis, FakeProducer]:
    repo = repository or FakeRepository()
    redis = redis_client or FakeRedis()
    event_producer = producer or FakeProducer()
    return (
        DebugLoggingService(
            repository=repo,  # type: ignore[arg-type]
            redis_client=redis,  # type: ignore[arg-type]
            settings=PlatformSettings(governance={"retention_days": 7}),
            producer=event_producer,  # type: ignore[arg-type]
        ),
        repo,
        redis,
        event_producer,
    )


@pytest.mark.asyncio
async def test_open_session_validates_conflicts_caches_and_publishes_event() -> None:
    service, repo, redis, producer = _service()
    target_id = uuid4()
    requested_by = uuid4()

    with pytest.raises(ValidationError):
        await service.open_session(
            target_type="invalid",
            target_id=target_id,
            justification="too short",
            duration_minutes=5,
            requested_by=requested_by,
            correlation_id=uuid4(),
        )
    with pytest.raises(ValidationError):
        await service.open_session(
            target_type="user",
            target_id=target_id,
            justification="too short",
            duration_minutes=5,
            requested_by=requested_by,
            correlation_id=uuid4(),
        )
    with pytest.raises(ValidationError):
        await service.open_session(
            target_type="user",
            target_id=target_id,
            justification="Long enough reason",
            duration_minutes=999,
            requested_by=requested_by,
            correlation_id=uuid4(),
        )

    debug_session = await service.open_session(
        target_type="user",
        target_id=target_id,
        justification=" Long enough reason ",
        duration_minutes=5,
        requested_by=requested_by,
        correlation_id=uuid4(),
    )

    assert debug_session.justification == "Long enough reason"
    assert redis.cache[(DEBUG_SESSION_CACHE_CONTEXT, f"user:{target_id}")]["session_id"] == str(
        debug_session.id
    )
    assert producer.events[-1][0] == "debug_logging.session.created"
    with pytest.raises(DebugLoggingConflictError):
        await service.open_session(
            target_type="user",
            target_id=target_id,
            justification="Another long enough reason",
            duration_minutes=5,
            requested_by=requested_by,
            correlation_id=uuid4(),
        )
    assert repo.sessions[debug_session.id] is debug_session


@pytest.mark.asyncio
async def test_find_active_session_uses_cache_sentinel_and_expires_stale_cached_session() -> None:
    service, repo, redis, producer = _service()
    target_id = uuid4()
    active = _session(target_id=target_id)
    expired = _session(
        target_id=target_id,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    repo.sessions[active.id] = active
    repo.sessions[expired.id] = expired

    redis.cache[(DEBUG_SESSION_CACHE_CONTEXT, f"user:{target_id}")] = {
        "session_id": DEBUG_SESSION_SENTINEL
    }
    assert await service.find_active_session("user", target_id) is None

    redis.cache[(DEBUG_SESSION_CACHE_CONTEXT, f"user:{target_id}")] = {
        "session_id": str(active.id)
    }
    assert await service.find_active_session("user", target_id) is active

    redis.cache[(DEBUG_SESSION_CACHE_CONTEXT, f"user:{target_id}")] = {
        "session_id": "not-a-uuid"
    }
    repo.active_by_target[("user", target_id)] = None
    assert await service.find_active_session("user", target_id) is None

    redis.cache[(DEBUG_SESSION_CACHE_CONTEXT, f"user:{target_id}")] = {
        "session_id": str(expired.id)
    }
    assert await service.find_active_session("user", target_id) is None
    assert expired.termination_reason == DebugLoggingTerminationReason.expired.value
    assert (DEBUG_SESSION_CACHE_CONTEXT, f"user:{target_id}") in redis.deleted
    assert producer.events[-1][0] == "debug_logging.session.expired"


@pytest.mark.asyncio
async def test_record_capture_and_termination_paths() -> None:
    service, repo, redis, producer = _service()
    requester = uuid4()
    debug_session = _session(requested_by=requester)
    repo.sessions[debug_session.id] = debug_session

    capture = await service.record_capture(
        debug_session.id,
        method="POST",
        path="/api/v1/items",
        request_headers={"authorization": "[REDACTED]"},
        request_body="{}",
        response_status=201,
        response_headers={"content-type": "application/json"},
        response_body='{"ok":true}',
        duration_ms=-5,
        correlation_id=debug_session.correlation_id,
    )
    if service._background_tasks:
        await service._background_tasks.pop()

    assert capture is not None
    assert capture.duration_ms == 0
    assert repo.incremented == [debug_session.id]
    assert producer.events[-1][0] == "debug_logging.capture.written"

    with pytest.raises(AuthorizationError):
        await service.terminate_session(debug_session.id, actor_id=uuid4(), is_superadmin=False)

    terminated = await service.terminate_session(
        debug_session.id,
        actor_id=requester,
        is_superadmin=False,
    )

    assert terminated.termination_reason == DebugLoggingTerminationReason.manual_close.value
    assert (DEBUG_SESSION_CACHE_CONTEXT, f"user:{debug_session.target_id}") in redis.deleted
    with pytest.raises(DebugLoggingConflictError):
        await service.terminate_session(debug_session.id, actor_id=requester, is_superadmin=True)
    assert await service.record_capture(
        debug_session.id,
        method="GET",
        path="/inactive",
        request_headers={},
        request_body=None,
        response_status=200,
        response_headers={},
        response_body=None,
        duration_ms=1,
        correlation_id=debug_session.correlation_id,
    ) is None


@pytest.mark.asyncio
async def test_list_get_purge_and_repository_helpers(monkeypatch) -> None:
    service, repo, _, _ = _service()
    debug_session = _session(target_type="workspace")
    repo.sessions[debug_session.id] = debug_session
    capture = DebugLoggingCapture(
        id=uuid4(),
        session_id=debug_session.id,
        captured_at=datetime.now(UTC),
        method="GET",
        path="/debug",
        request_headers={},
        request_body=None,
        response_status=200,
        response_headers={},
        response_body=None,
        duration_ms=3,
        correlation_id=debug_session.correlation_id,
    )
    repo.captures.append(capture)

    assert await service.get_session(debug_session.id) is debug_session
    assert (await service.list_sessions(
        active_only=True,
        requested_by=None,
        target_type="workspace",
        target_id=debug_session.target_id,
        limit=10,
        cursor=None,
    ))[0] == [debug_session]
    assert (await service.list_captures(debug_session.id, limit=10, cursor=None))[0] == [capture]
    assert await service.purge_old_captures() == 3

    managed = FakeManagedSession(repo)
    monkeypatch.setattr(
        "platform.common.debug_logging.service.DebugLoggingRepository",
        lambda session: session.repository,
    )
    deleted = await purge_debug_captures(
        session_factory=lambda: managed,  # type: ignore[return-value]
        redis_client=FakeRedis(),  # type: ignore[arg-type]
        settings=PlatformSettings(governance={"retention_days": 7}),
    )

    assert deleted == 3
    assert managed.committed is True
    failing_managed = FakeManagedSession(repo, fail_commit=True)
    with pytest.raises(RuntimeError):
        await purge_debug_captures(
            session_factory=lambda: failing_managed,  # type: ignore[return-value]
            redis_client=FakeRedis(),  # type: ignore[arg-type]
            settings=PlatformSettings(governance={"retention_days": 7}),
        )
    assert failing_managed.rolled_back is True
    await publish_debug_logging_event(
        "debug_logging.session.expired",
        DebugLoggingSessionExpiredPayload(
            session_id=debug_session.id,
            duration_ms=1,
            capture_count=0,
            termination_reason="expired",
        ),
        debug_session.correlation_id,
        None,
    )

    items = [_session(), _session(), _session()]
    page, cursor = _page(items, 2, lambda item: item.started_at)
    assert page == items[:2]
    assert cursor is not None
    assert _apply_cursor(object(), object(), object(), None) is not None


@pytest.mark.asyncio
async def test_debug_logging_repository_methods_with_fake_session() -> None:
    debug_session = _session()
    capture = DebugLoggingCapture(
        id=uuid4(),
        session_id=debug_session.id,
        captured_at=datetime.now(UTC),
        method="GET",
        path="/debug",
        request_headers={},
        request_body=None,
        response_status=200,
        response_headers={},
        response_body=None,
        duration_ms=1,
        correlation_id=debug_session.correlation_id,
    )
    fake_session = FakeSession(
        [
            FakeScalarResult([debug_session]),
            FakeScalarResult([debug_session]),
            FakeScalarResult([debug_session, _session()]),
            FakeScalarResult(),
            FakeScalarResult([capture, capture]),
            FakeScalarResult(rowcount=2),
        ]
    )
    repository = DebugLoggingRepository(fake_session)  # type: ignore[arg-type]

    assert await repository.create_session(debug_session) is debug_session
    assert await repository.get_session(debug_session.id) is debug_session
    assert await repository.find_active_session_for_target("user", debug_session.target_id)
    sessions, next_cursor = await repository.list_sessions(
        active_only=True,
        requested_by=debug_session.requested_by,
        target_type="user",
        target_id=debug_session.target_id,
        limit=1,
        cursor=None,
    )
    assert sessions == [debug_session]
    assert next_cursor is not None
    assert await repository.terminate_session(
        debug_session,
        terminated_at=datetime.now(UTC),
        termination_reason="manual_close",
    ) is debug_session
    assert await repository.append_capture(capture) is capture
    await repository.increment_capture_count(debug_session.id)
    captures, capture_cursor = await repository.list_captures(
        debug_session.id,
        limit=1,
        cursor=None,
    )
    assert captures == [capture]
    assert capture_cursor is not None
    assert await repository.purge_old_captures(datetime.now(UTC)) == 2
    assert fake_session.flush_count == 3


@pytest.mark.asyncio
async def test_debug_logging_router_functions_delegate_and_authorize() -> None:
    service, repo, _, _ = _service()
    requester = uuid4()
    target_id = uuid4()
    correlation_id = uuid4()
    admin_user = {
        "sub": str(requester),
        "roles": [{"role": "platform_admin"}, {"role": "auditor"}],
    }
    auditor_user = {"sub": str(requester), "roles": [{"role": "auditor"}]}
    request = SimpleNamespace(state=SimpleNamespace(correlation_id=correlation_id))

    assert _role_names(admin_user) == {"platform_admin", "auditor"}
    assert _role_names({"roles": "platform_admin"}) == set()
    assert _is_superadmin({"roles": [{"role": "superadmin"}]}) is True
    assert _actor_id(admin_user) == requester
    _require_read_access(auditor_user)
    _require_write_access(admin_user)
    with pytest.raises(AuthorizationError):
        _require_read_access({"roles": [{"role": "viewer"}]})
    with pytest.raises(AuthorizationError):
        _require_write_access(auditor_user)
    with pytest.raises(ValidationError):
        _actor_id({"sub": "not-a-uuid", "roles": []})
    assert _correlation_id(SimpleNamespace(state=SimpleNamespace(correlation_id="bad"))) == UUID(
        int=0
    )
    built_service = await get_debug_logging_service(
        request=SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    settings=PlatformSettings(),
                    clients={"redis": FakeRedis(), "kafka": None},
                )
            )
        ),  # type: ignore[arg-type]
        db=object(),  # type: ignore[arg-type]
    )
    assert isinstance(built_service, DebugLoggingService)

    created = await open_debug_logging_session(
        payload=DebugLoggingSessionCreateRequest(
            target_type="user",
            target_id=target_id,
            justification="Need request trace",
            duration_minutes=5,
        ),
        request=request,  # type: ignore[arg-type]
        current_user=admin_user,
        service=service,
    )
    session_id = created.session_id
    debug_session = repo.sessions[session_id]
    await service.record_capture(
        session_id,
        method="GET",
        path="/api/v1/example",
        request_headers={},
        request_body=None,
        response_status=200,
        response_headers={},
        response_body=None,
        duration_ms=1,
        correlation_id=correlation_id,
    )
    if service._background_tasks:
        await service._background_tasks.pop()

    listed = await list_debug_logging_sessions(
        active_only=True,
        requested_by=None,
        target_type="user",
        target_id=target_id,
        limit=10,
        cursor=None,
        current_user=auditor_user,
        service=service,
    )
    fetched = await get_debug_logging_session(
        session_id=session_id,
        current_user=auditor_user,
        service=service,
    )
    captures = await list_debug_logging_captures(
        session_id=session_id,
        limit=10,
        cursor=None,
        current_user=auditor_user,
        service=service,
    )
    response = await terminate_debug_logging_session(
        session_id=session_id,
        current_user=admin_user,
        service=service,
    )

    assert listed.items[0].session_id == session_id
    assert fetched.target_id == debug_session.target_id
    assert captures.items[0].path == "/api/v1/example"
    assert response.status_code == 204
    with pytest.raises(DebugLoggingMethodNotAllowedError):
        await patch_debug_logging_session(
            session_id=session_id,
            current_user=admin_user,
        )


@pytest.mark.asyncio
async def test_debug_capture_middleware_helpers_and_non_http_passthrough() -> None:
    received_scope_types: list[str] = []
    sent_messages: list[dict[str, object]] = []

    async def app(scope, receive, send) -> None:
        del receive
        received_scope_types.append(scope["type"])
        await send({"type": "websocket.close"})

    middleware = DebugCaptureMiddleware(app)

    async def receive() -> dict[str, object]:
        return {"type": "websocket.receive"}

    async def send(message: dict[str, object]) -> None:
        sent_messages.append(message)

    await middleware({"type": "websocket"}, receive, send)  # type: ignore[arg-type]

    user_id = uuid4()
    workspace_id = uuid4()
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/items",
            "query_string": b"token=secret",
            "headers": [(b"x-workspace-id", str(workspace_id).encode("ascii"))],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )
    request.state.user = {"principal_type": "user", "principal_id": str(user_id)}
    request.state.correlation_id = "not-a-uuid"

    assert received_scope_types == ["websocket"]
    assert sent_messages == [{"type": "websocket.close"}]
    assert DebugCaptureMiddleware._candidate_targets(request) == [
        ("user", user_id),
        ("workspace", workspace_id),
    ]
    assert DebugCaptureMiddleware._raw_path(request) == "/api/v1/items?token=secret"
    assert DebugCaptureMiddleware._correlation_id(request) == UUID(int=0)

    invalid_workspace_request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/items",
            "query_string": b"",
            "headers": [(b"x-workspace-id", b"not-a-uuid")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )
    assert DebugCaptureMiddleware._candidate_targets(invalid_workspace_request) == []
    assert DebugCaptureMiddleware._raw_path(invalid_workspace_request) == "/api/v1/items"


@pytest.mark.asyncio
async def test_debug_capture_middleware_records_redacted_http_exchange(monkeypatch) -> None:
    user_id = uuid4()
    workspace_id = uuid4()
    session_id = uuid4()
    correlation_id = uuid4()
    sent_messages: list[dict[str, object]] = []
    records: list[dict[str, object]] = []

    class CaptureService:
        def __init__(self, **kwargs) -> None:
            del kwargs

        async def find_active_session(
            self,
            target_type: str,
            target_id: UUID,
        ) -> SimpleNamespace | None:
            if (target_type, target_id) == ("user", user_id):
                return SimpleNamespace(id=session_id)
            return None

        async def record_capture(self, session_id: UUID, **kwargs) -> None:
            records.append({"session_id": session_id, **kwargs})

    class CaptureSession:
        def __init__(self) -> None:
            self.committed = False

        async def __aenter__(self) -> CaptureSession:
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            del exc_type, exc, traceback

        async def commit(self) -> None:
            self.committed = True

    async def app(scope, receive, send) -> None:
        del scope
        first = await receive()
        second = await receive()
        assert first["body"] == b'{"password":"secret"}'
        assert second["body"] == b""
        await send(
            {
                "type": "http.response.start",
                "status": 201,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"set-cookie", b"session=secret"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b'{"token":"secret"}'})

    monkeypatch.setattr("platform.common.debug_logging.capture.AsyncRedisClient", FakeRedis)
    monkeypatch.setattr(
        "platform.common.debug_logging.capture.database.AsyncSessionLocal",
        CaptureSession,
    )
    monkeypatch.setattr(
        "platform.common.debug_logging.capture.DebugLoggingRepository",
        lambda session: session,
    )
    monkeypatch.setattr(
        "platform.common.debug_logging.capture.DebugLoggingService",
        CaptureService,
    )
    middleware = DebugCaptureMiddleware(app)
    receive_messages = [
        {
            "type": "http.request",
            "body": b'{"password":"secret"}',
            "more_body": False,
        }
    ]

    async def receive() -> dict[str, object]:
        return receive_messages.pop(0)

    async def send(message: dict[str, object]) -> None:
        sent_messages.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/items",
        "query_string": b"access_token=secret&keep=yes",
        "headers": [
            (b"authorization", b"Bearer secret"),
            (b"content-type", b"application/json"),
            (b"x-workspace-id", str(workspace_id).encode("ascii")),
        ],
        "state": {
            "user": {"principal_type": "user", "principal_id": str(user_id)},
            "correlation_id": correlation_id,
        },
        "app": SimpleNamespace(
            state=SimpleNamespace(
                settings=PlatformSettings(),
                clients={"redis": FakeRedis(), "kafka": None},
            )
        ),
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }

    await middleware(scope, receive, send)  # type: ignore[arg-type]

    assert [message["type"] for message in sent_messages] == [
        "http.response.start",
        "http.response.body",
    ]
    assert records[0]["session_id"] == session_id
    assert records[0]["path"] == "/api/v1/items?keep=yes"
    assert records[0]["request_headers"]["authorization"] == "[REDACTED]"
    assert records[0]["request_body"] == '{"password": "[REDACTED]"}'
    assert records[0]["response_headers"]["set-cookie"] == "[REDACTED]"
    assert records[0]["response_body"] == '{"token": "[REDACTED]"}'


@pytest.mark.asyncio
async def test_debug_capture_middleware_handles_capture_errors_and_non_redis_client(
    monkeypatch,
) -> None:
    sent_messages: list[dict[str, object]] = []

    async def app(scope, receive, send) -> None:
        del scope
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = DebugCaptureMiddleware(app)

    async def failing_capture(*args, **kwargs) -> None:
        del args, kwargs
        raise RuntimeError("capture failed")

    monkeypatch.setattr(middleware, "_capture_if_needed", failing_capture)

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"{}", "more_body": False}

    async def send(message: dict[str, object]) -> None:
        sent_messages.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/items",
        "query_string": b"",
        "headers": [],
        "state": {},
        "app": SimpleNamespace(state=SimpleNamespace(settings=PlatformSettings(), clients={})),
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }

    await middleware(scope, receive, send)  # type: ignore[arg-type]

    assert [message["type"] for message in sent_messages] == [
        "http.response.start",
        "http.response.body",
    ]

    request = Request(
        {
            **scope,
            "headers": [(b"x-workspace-id", str(uuid4()).encode("ascii"))],
            "app": SimpleNamespace(
                state=SimpleNamespace(settings=PlatformSettings(), clients={"redis": object()})
            ),
        }
    )
    await DebugCaptureMiddleware(app)._capture_if_needed(
        request,
        request_body=b"",
        response_status=200,
        response_headers={},
        response_body=b"",
        duration_ms=1,
    )
