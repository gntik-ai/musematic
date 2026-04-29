from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from platform.admin.change_preview import (
    build_change_preview,
    classify_irreversibility,
    compute_affected_count,
    estimate_duration,
)
from platform.admin.config_export_service import ConfigExportService, _redacted_config, _tar_bundle
from platform.admin.config_import_service import ConfigImportService, _extract_bundle
from platform.admin.feature_flags_service import (
    FEATURE_FLAG_DEFAULTS,
    FeatureFlagsService,
)
from platform.admin.impersonation_models import ImpersonationSession
from platform.admin.impersonation_service import (
    IMPERSONATE_SUPERADMIN_ACTION,
    ImpersonationService,
)
from platform.admin.read_only_middleware import (
    AdminReadOnlyMiddleware,
    _admin_read_only_mode,
    _uuid_or_none,
)
from platform.admin.responses import accepted, empty_detail, empty_list, tenant_id_from_user
from platform.admin.tenant_mode_service import (
    TENANT_MODE_DOWNGRADE_ACTION,
    TENANT_MODE_UPGRADE_ACTION,
    TenantModeService,
)
from platform.admin.two_person_auth_models import TwoPersonAuthRequest
from platform.admin.two_person_auth_service import (
    TWO_PERSON_AUTH_TOKEN_TYPE,
    TwoPersonAuthService,
)
from platform.auth.session import RedisSessionStore
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.exceptions import AuthorizationError, NotFoundError, ValidationError
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import jwt
import pytest
import yaml
from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from tests.auth_support import MemoryRedis


class _Scalars:
    def __init__(self, values: list[Any]) -> None:
        self._values = values

    def all(self) -> list[Any]:
        return self._values


class _Mappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[dict[str, Any]]:
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class _Result:
    def __init__(
        self,
        *,
        scalar: Any = None,
        scalars: list[Any] | None = None,
        mappings: list[dict[str, Any]] | None = None,
        rows: list[Any] | None = None,
        rowcount: int = 0,
    ) -> None:
        self._scalar = scalar
        self._scalars = scalars or []
        self._mappings = mappings or []
        self._rows = rows or []
        self.rowcount = rowcount

    def scalar_one_or_none(self) -> Any:
        return self._scalar

    def scalars(self) -> _Scalars:
        return _Scalars(self._scalars)

    def mappings(self) -> _Mappings:
        return _Mappings(self._mappings)

    def one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class _QueueSession:
    def __init__(self, execute_results: list[_Result] | None = None) -> None:
        self.execute_results = execute_results or []
        self.executed: list[dict[str, Any] | None] = []
        self.added: list[Any] = []
        self.get_rows: dict[UUID, Any] = {}
        self.flushes = 0

    def add(self, row: Any) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        self.flushes += 1

    async def get(self, _model: type[Any], row_id: UUID) -> Any:
        return self.get_rows.get(row_id)

    async def execute(self, _statement: Any, params: dict[str, Any] | None = None) -> _Result:
        self.executed.append(params)
        if self.execute_results:
            return self.execute_results.pop(0)
        return _Result()


class _Signing:
    def __init__(self, verify_result: bool = True) -> None:
        self.verify_result = verify_result
        self.signed: list[bytes] = []
        self.verified: list[tuple[bytes, bytes, str]] = []

    def sign(self, payload: bytes) -> bytes:
        self.signed.append(payload)
        return b"signature"

    def verify(self, payload: bytes, signature: bytes, source_key: str) -> bool:
        self.verified.append((payload, signature, source_key))
        return self.verify_result


class _AuditChain:
    def __init__(self, verify_result: bool = True) -> None:
        self.signing = _Signing(verify_result)
        self.appended: list[dict[str, Any]] = []

    async def get_public_verifying_key(self) -> str:
        return "public-key"

    async def append(self, *_args: Any, **kwargs: Any) -> None:
        self.appended.append(kwargs)


def _actor(user_id: UUID | None = None, roles: list[str] | None = None) -> dict[str, Any]:
    return {
        "sub": str(user_id or uuid4()),
        "session_id": str(uuid4()),
        "roles": roles or ["superadmin"],
    }


def _two_person_request(
    *,
    request_id: UUID | None = None,
    action: str = "admin.action",
    initiator_id: UUID | None = None,
    expires_at: datetime | None = None,
    approved_at: datetime | None = None,
    rejected_at: datetime | None = None,
    consumed: bool = False,
) -> TwoPersonAuthRequest:
    now = datetime.now(UTC)
    request = TwoPersonAuthRequest(
        request_id=request_id or uuid4(),
        action=action,
        payload={"target": "demo"},
        initiator_id=initiator_id or uuid4(),
        created_at=now,
        expires_at=expires_at or now + timedelta(minutes=10),
        consumed=consumed,
    )
    request.approved_at = approved_at
    request.rejected_at = rejected_at
    return request


@pytest.mark.asyncio
async def test_two_person_auth_lifecycle_approves_and_consumes_token(
    auth_settings: PlatformSettings,
) -> None:
    session = _QueueSession()
    service = TwoPersonAuthService(session, auth_settings)
    initiator_id = uuid4()
    approver_id = uuid4()

    created = await service.initiate("admin.action", {"target": "demo"}, {"sub": initiator_id})
    session.execute_results.extend([_Result(scalar=created), _Result(scalar=created)])

    token = await service.approve(created.request_id, approver_id)
    validated = await service.validate_token(token, "admin.action")

    assert created.initiator_id == initiator_id
    assert created.approved_by_id == approver_id
    assert validated is True
    assert created.consumed is True
    assert session.flushes == 3


@pytest.mark.asyncio
async def test_two_person_auth_rejects_invalid_approval_states(
    auth_settings: PlatformSettings,
) -> None:
    now = datetime.now(UTC)
    actor_id = uuid4()
    service = TwoPersonAuthService(_QueueSession([_Result(scalar=None)]), auth_settings)
    with pytest.raises(NotFoundError):
        await service.approve(uuid4(), uuid4())

    cases = [
        (_two_person_request(initiator_id=actor_id), actor_id, AuthorizationError),
        (
            _two_person_request(expires_at=now - timedelta(seconds=1)),
            uuid4(),
            ValidationError,
        ),
        (_two_person_request(rejected_at=now), uuid4(), ValidationError),
        (_two_person_request(consumed=True), uuid4(), ValidationError),
    ]
    for request, approver_id, error_type in cases:
        service = TwoPersonAuthService(_QueueSession([_Result(scalar=request)]), auth_settings)
        with pytest.raises(error_type):
            await service.approve(request.request_id, approver_id)

    approved = _two_person_request(approved_at=now)
    service = TwoPersonAuthService(_QueueSession([_Result(scalar=approved)]), auth_settings)
    with pytest.raises(ValidationError):
        await service.reject(approved.request_id, uuid4(), "duplicate")

    consumed = _two_person_request(consumed=True)
    service = TwoPersonAuthService(_QueueSession([_Result(scalar=consumed)]), auth_settings)
    with pytest.raises(ValidationError):
        await service.reject(consumed.request_id, uuid4(), "too late")


@pytest.mark.asyncio
async def test_two_person_auth_validate_token_false_paths(
    auth_settings: PlatformSettings,
) -> None:
    service = TwoPersonAuthService(_QueueSession(), auth_settings)

    assert await service.validate_token("not-a-jwt", "admin.action") is False

    def encode(payload: dict[str, Any]) -> str:
        return jwt.encode(
            payload,
            auth_settings.auth.signing_key,
            algorithm=auth_settings.auth.jwt_algorithm,
        )

    assert await service.validate_token(encode({"type": "other"}), "admin.action") is False
    assert (
        await service.validate_token(
            encode({"type": TWO_PERSON_AUTH_TOKEN_TYPE, "action": "wrong", "sub": str(uuid4())}),
            "admin.action",
        )
        is False
    )
    assert (
        await service.validate_token(
            encode({"type": TWO_PERSON_AUTH_TOKEN_TYPE, "action": "admin.action", "sub": "bad"}),
            "admin.action",
        )
        is False
    )

    missing = TwoPersonAuthService(_QueueSession([_Result(scalar=None)]), auth_settings)
    assert (
        await missing.validate_token(
            encode(
                {
                    "type": TWO_PERSON_AUTH_TOKEN_TYPE,
                    "action": "admin.action",
                    "sub": str(uuid4()),
                }
            ),
            "admin.action",
        )
        is False
    )

    invalid_requests = [
        _two_person_request(),
        _two_person_request(action="different", approved_at=datetime.now(UTC)),
        _two_person_request(approved_at=datetime.now(UTC), rejected_at=datetime.now(UTC)),
        _two_person_request(
            approved_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        ),
        _two_person_request(approved_at=datetime.now(UTC), consumed=True),
    ]
    for request in invalid_requests:
        token = encode(
            {
                "type": TWO_PERSON_AUTH_TOKEN_TYPE,
                "action": "admin.action",
                "sub": str(request.request_id),
            }
        )
        service = TwoPersonAuthService(_QueueSession([_Result(scalar=request)]), auth_settings)
        assert await service.validate_token(token, "admin.action") is False


@pytest.mark.asyncio
async def test_two_person_auth_list_get_reject_and_expire(auth_settings: PlatformSettings) -> None:
    request = _two_person_request()
    session = _QueueSession(
        [
            _Result(scalar=request),
            _Result(scalars=[request]),
            _Result(rowcount=2),
        ]
    )
    session.get_rows[request.request_id] = request
    service = TwoPersonAuthService(session, auth_settings)

    await service.reject(request.request_id, uuid4(), "not approved")
    pending = await service.list_pending()
    fetched = await service.get(request.request_id)
    expired = await service.expire_requests(datetime.now(UTC))

    assert request.rejected_by_id is not None
    assert pending == [request]
    assert fetched is request
    assert expired == 2

    with pytest.raises(NotFoundError):
        await service.get(uuid4())


class _Notifications:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create_admin_alert(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


class _TwoPersonGate:
    def __init__(self, result: bool) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    async def validate_token(self, token: str, action: str) -> bool:
        self.calls.append((token, action))
        return self.result


def _impersonation_row(
    *,
    session_id: UUID | None = None,
    impersonating_user_id: UUID | None = None,
    effective_user_id: UUID | None = None,
    expires_at: datetime | None = None,
) -> ImpersonationSession:
    now = datetime.now(UTC)
    return ImpersonationSession(
        session_id=session_id or uuid4(),
        impersonating_user_id=impersonating_user_id or uuid4(),
        effective_user_id=effective_user_id or uuid4(),
        justification="Need to investigate a tenant support escalation.",
        started_at=now,
        expires_at=expires_at or now + timedelta(minutes=10),
    )


@pytest.mark.asyncio
async def test_impersonation_start_issues_token_and_notifies_user(
    auth_settings: PlatformSettings,
) -> None:
    target_id = uuid4()
    notifications = _Notifications()
    session = _QueueSession(
        [
            _Result(scalar=None),
            _Result(mappings=[{"id": target_id, "email": "target@example.test"}]),
            _Result(rows=[SimpleNamespace(role="viewer", workspace_id=None)]),
        ]
    )
    actor = _actor()
    service = ImpersonationService(session, auth_settings, notifications=notifications)

    row, token = await service.start(
        actor,
        target_id,
        "Need to investigate a tenant support escalation.",
    )
    payload = jwt.decode(
        token,
        auth_settings.auth.verification_key,
        algorithms=[auth_settings.auth.jwt_algorithm],
    )

    assert row in session.added
    assert payload["sub"] == str(target_id)
    assert payload["impersonation_user_id"] == actor["sub"]
    assert notifications.calls[0]["alert_type"] == "admin_impersonation_started"


@pytest.mark.asyncio
async def test_impersonation_start_rejects_invalid_states(
    auth_settings: PlatformSettings,
) -> None:
    service = ImpersonationService(_QueueSession(), auth_settings)
    with pytest.raises(ValidationError):
        await service.start(_actor(), uuid4(), "too short")

    active = _impersonation_row()
    service = ImpersonationService(_QueueSession([_Result(scalar=active)]), auth_settings)
    with pytest.raises(ValidationError):
        await service.start(_actor(), uuid4(), "Need to investigate a tenant support escalation.")

    service = ImpersonationService(
        _QueueSession([_Result(scalar=None), _Result(mappings=[])]),
        auth_settings,
    )
    with pytest.raises(NotFoundError):
        await service.start(_actor(), uuid4(), "Need to investigate a tenant support escalation.")


@pytest.mark.asyncio
async def test_impersonation_superadmin_requires_and_consumes_2pa(
    auth_settings: PlatformSettings,
) -> None:
    target_id = uuid4()
    rows = [
        _Result(scalar=None),
        _Result(mappings=[{"id": target_id, "email": "super@example.test"}]),
        _Result(rows=[SimpleNamespace(role="superadmin", workspace_id=None)]),
    ]
    service = ImpersonationService(_QueueSession(rows), auth_settings, _TwoPersonGate(True))
    with pytest.raises(AuthorizationError):
        await service.start(_actor(), target_id, "Need to investigate another super admin.")

    invalid_gate = _TwoPersonGate(False)
    rows = [
        _Result(scalar=None),
        _Result(mappings=[{"id": target_id, "email": "super@example.test"}]),
        _Result(rows=[SimpleNamespace(role="superadmin", workspace_id=None)]),
    ]
    service = ImpersonationService(_QueueSession(rows), auth_settings, invalid_gate)
    with pytest.raises(AuthorizationError):
        await service.start(
            _actor(),
            target_id,
            "Need to investigate another super admin.",
            two_person_auth_token="bad",
        )
    assert invalid_gate.calls == [("bad", IMPERSONATE_SUPERADMIN_ACTION)]

    valid_gate = _TwoPersonGate(True)
    rows = [
        _Result(scalar=None),
        _Result(mappings=[{"id": target_id, "email": "super@example.test"}]),
        _Result(rows=[SimpleNamespace(role="superadmin", workspace_id=uuid4())]),
        _Result(),
    ]
    session = _QueueSession(rows)
    service = ImpersonationService(session, auth_settings, valid_gate)
    row, _token = await service.start(
        _actor(),
        target_id,
        "Need to investigate another super admin.",
        two_person_auth_token="good",
    )

    assert row in session.added
    assert session.executed[-1]["alert_type"] == "admin_impersonation_started"


@pytest.mark.asyncio
async def test_impersonation_end_and_expire_paths(auth_settings: PlatformSettings) -> None:
    notifications = _Notifications()
    row = _impersonation_row()
    session = _QueueSession()
    session.get_rows[row.session_id] = row
    service = ImpersonationService(session, auth_settings, notifications=notifications)

    await service.end(row.session_id, "ended_by_admin")
    await service.end(row.session_id, "already_ended")

    assert row.ended_at is not None
    assert row.end_reason == "ended_by_admin"
    assert [call["alert_type"] for call in notifications.calls] == ["admin_impersonation_ended"]

    with pytest.raises(NotFoundError):
        await service.end(uuid4(), "missing")

    expired = _impersonation_row(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    session = _QueueSession([_Result(scalars=[expired])])
    service = ImpersonationService(session, auth_settings, notifications=_Notifications())
    assert await service.expire_sessions(datetime.now(UTC)) == 1
    assert expired.end_reason == "expired"


@pytest.mark.asyncio
async def test_feature_flags_list_set_delete_and_validate() -> None:
    actor = _actor()
    audit_chain = _AuditChain()
    workspace_id = uuid4()
    service = FeatureFlagsService(
        _QueueSession(
            [
                _Result(
                    mappings=[
                        {
                            "id": uuid4(),
                            "key": "FEATURE_DLP_ENABLED",
                            "value": {"enabled": False},
                            "scope": "workspace",
                            "scope_id": workspace_id,
                        }
                    ]
                ),
                _Result(
                    mappings=[
                        {
                            "id": uuid4(),
                            "key": "FEATURE_SIGNUP_ENABLED",
                            "value": {"enabled": False},
                            "scope": "global",
                            "scope_id": None,
                        }
                    ]
                ),
            ]
        ),
        audit_chain,
    )

    records = await service.list_flags(scope="workspace", scope_id=workspace_id)

    assert next(row for row in records if row.key == "FEATURE_DLP_ENABLED").inherited is False
    signup = next(row for row in records if row.key == "FEATURE_SIGNUP_ENABLED")
    assert signup.enabled is False
    assert signup.inherited is True

    insert_session = _QueueSession([_Result(mappings=[]), _Result()])
    inserted = await FeatureFlagsService(insert_session, audit_chain).set_flag(
        key="FEATURE_DLP_ENABLED",
        enabled=True,
        scope="global",
        scope_id=None,
        actor=actor,
    )
    update_session = _QueueSession(
        [
            _Result(mappings=[{"id": uuid4(), "value": {"enabled": False}}]),
            _Result(),
        ]
    )
    updated = await FeatureFlagsService(update_session, audit_chain).set_flag(
        key="FEATURE_DLP_ENABLED",
        enabled=True,
        scope="global",
        scope_id=None,
        actor=actor,
    )
    delete_session = _QueueSession(
        [
            _Result(mappings=[{"id": uuid4(), "value": {"enabled": True}}]),
            _Result(),
        ]
    )
    await FeatureFlagsService(delete_session, audit_chain).delete_override(
        key="FEATURE_DLP_ENABLED",
        scope="global",
        scope_id=None,
        actor=actor,
    )

    assert inserted.enabled is True
    assert updated.enabled is True
    assert len(audit_chain.appended) == 3

    missing = FeatureFlagsService(_QueueSession([_Result(mappings=[])]), audit_chain)
    with pytest.raises(NotFoundError):
        await missing.delete_override(
            key="FEATURE_DLP_ENABLED",
            scope="global",
            scope_id=None,
            actor=actor,
        )

    with pytest.raises(ValidationError):
        await service.list_flags(scope="invalid")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        await service.list_flags(scope="global", scope_id=uuid4())
    with pytest.raises(ValidationError):
        await service.list_flags(scope="workspace")
    with pytest.raises(ValidationError):
        await service.set_flag(
            key="UNKNOWN_FLAG",
            enabled=True,
            scope="global",
            scope_id=None,
            actor=actor,
        )


class _TenantSession(_QueueSession):
    def __init__(
        self,
        *,
        modes: list[Any] | None = None,
        rowcounts: list[int] | None = None,
        tenant_ids: list[UUID] | None = None,
    ) -> None:
        super().__init__()
        self.modes = modes or []
        self.rowcounts = rowcounts or []
        self.tenant_ids = tenant_ids or []

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Result:
        sql = str(statement)
        self.executed.append(params)
        if "SELECT value" in sql:
            return _Result(scalar=self.modes.pop(0))
        if "SELECT DISTINCT scope_id" in sql:
            return _Result(scalars=self.tenant_ids)
        if "UPDATE platform_settings" in sql:
            return _Result(rowcount=self.rowcounts.pop(0) if self.rowcounts else 0)
        return _Result()


@pytest.mark.asyncio
async def test_tenant_mode_upgrade_downgrade_and_2pa_paths() -> None:
    actor = _actor()
    audit_chain = _AuditChain()
    producer = SimpleNamespace(calls=[])

    async def publish(**kwargs: Any) -> None:
        producer.calls.append(kwargs)

    producer.publish = publish
    service = TenantModeService(
        _TenantSession(modes=["single"], rowcounts=[0]),
        _TwoPersonGate(True),
        audit_chain,
        producer,
    )
    upgraded = await service.upgrade_to_multi(actor=actor, two_person_auth_token="token")

    assert upgraded == {"previous_mode": "single", "tenant_mode": "multi"}
    assert producer.calls[0]["event_type"] == "admin.tenant_mode.changed"

    tenant_ids = [uuid4(), uuid4()]
    service = TenantModeService(
        _TenantSession(tenant_ids=tenant_ids),
        _TwoPersonGate(True),
        audit_chain,
    )
    with pytest.raises(ValidationError):
        await service.downgrade_to_single(actor=actor, two_person_auth_token="token")

    service = TenantModeService(
        _TenantSession(modes=["unexpected"], rowcounts=[1], tenant_ids=[tenant_ids[0]]),
        _TwoPersonGate(True),
        audit_chain,
    )
    downgraded = await service.downgrade_to_single(actor=actor, two_person_auth_token="token")

    assert downgraded["previous_mode"] == "single"
    assert downgraded["tenant_mode"] == "single"
    assert downgraded["blocking_tenant_ids"] == [str(tenant_ids[0])]

    service = TenantModeService(_TenantSession(), _TwoPersonGate(True), audit_chain)
    with pytest.raises(AuthorizationError):
        await service.upgrade_to_multi(actor=actor, two_person_auth_token=None)

    service = TenantModeService(_TenantSession(), _TwoPersonGate(False), audit_chain)
    with pytest.raises(AuthorizationError):
        await service.upgrade_to_multi(actor=actor, two_person_auth_token="bad")

    assert _TwoPersonGate(True).result is True
    assert TENANT_MODE_UPGRADE_ACTION.endswith("upgrade_to_multi")
    assert TENANT_MODE_DOWNGRADE_ACTION.endswith("downgrade_to_single")


def _request(path: str, method: str, user: dict[str, Any] | None = None) -> Request:
    request = Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    if user is not None:
        request.state.user = user
    request.state.correlation_id = "corr-1"
    return request


def _attach_app(request: Request, app: FastAPI) -> Request:
    request.scope["app"] = app
    return request


class _ReadOnlySession:
    def __init__(self, value: bool) -> None:
        self.value = value

    async def execute(self, _statement: Any, _params: dict[str, Any]) -> _Result:
        return _Result(scalar=self.value)


class _ReadOnlyFactory:
    def __init__(self, value: bool) -> None:
        self.value = value

    def __call__(self) -> _ReadOnlyFactory:
        return self

    async def __aenter__(self) -> _ReadOnlySession:
        return _ReadOnlySession(self.value)

    async def __aexit__(self, *_args: Any) -> None:
        return None


@pytest.mark.asyncio
async def test_admin_read_only_middleware_and_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    session_id = uuid4()

    assert _uuid_or_none(user_id) == user_id
    assert _uuid_or_none("not-a-uuid") is None
    assert await _admin_read_only_mode(_request("/api/v1/admin/users", "POST")) is False
    assert (
        await _admin_read_only_mode(
            _request(
                "/api/v1/admin/users",
                "POST",
                {"sub": str(user_id), "session_id": str(session_id), "admin_read_only_mode": True},
            )
        )
        is True
    )
    assert (
        await _admin_read_only_mode(
            _request("/api/v1/admin/users", "POST", {"sub": "bad", "session_id": str(session_id)})
        )
        is False
    )

    monkeypatch.setattr(
        "platform.admin.read_only_middleware.database.AsyncSessionLocal",
        _ReadOnlyFactory(True),
    )
    assert (
        await _admin_read_only_mode(
            _request(
                "/api/v1/admin/users",
                "POST",
                {"sub": str(user_id), "session_id": str(session_id)},
            )
        )
        is True
    )

    middleware = AdminReadOnlyMiddleware(FastAPI())

    async def call_next(_request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    read_response = await middleware.dispatch(_request("/api/v1/admin/users", "GET"), call_next)
    blocked = await middleware.dispatch(
        _request(
            "/api/v1/admin/users",
            "POST",
            {"sub": str(user_id), "session_id": str(session_id), "admin_read_only_mode": True},
        ),
        call_next,
    )

    assert read_response.status_code == 200
    assert blocked.status_code == 403
    assert json.loads(blocked.body)["error"]["correlation_id"] == "corr-1"


@pytest.mark.asyncio
async def test_admin_read_only_middleware_checks_redis_session_state(
    auth_settings: PlatformSettings,
) -> None:
    user_id = uuid4()
    session_id = uuid4()
    redis_client = AsyncRedisClient(nodes=["localhost:6379"])
    redis_client.client = MemoryRedis()  # type: ignore[assignment]
    store = RedisSessionStore(redis_client, auth_settings.auth)
    app = FastAPI()
    app.state.clients = {"redis": redis_client}
    app.state.settings = auth_settings

    await store.create_session(
        user_id=user_id,
        session_id=session_id,
        email="admin@example.com",
        roles=[{"role": "platform_admin", "workspace_id": None}],
        ip="127.0.0.1",
        device="pytest",
        refresh_jti="refresh-1",
    )

    await store.set_admin_read_only_mode(user_id, session_id, True)
    assert (
        await _admin_read_only_mode(
            _attach_app(
                _request(
                    "/api/v1/admin/users",
                    "POST",
                    {"sub": str(user_id), "session_id": str(session_id)},
                ),
                app,
            )
        )
        is True
    )

    await store.set_admin_read_only_mode(user_id, session_id, False)
    assert (
        await _admin_read_only_mode(
            _attach_app(
                _request(
                    "/api/v1/admin/users",
                    "POST",
                    {"sub": str(user_id), "session_id": str(session_id)},
                ),
                app,
            )
        )
        is False
    )


def test_change_preview_helpers_cover_count_classification_and_duration() -> None:
    assert compute_affected_count(SimpleNamespace(affected_count="7"), object()) == 7
    assert compute_affected_count(object(), SimpleNamespace(count=lambda: 3)) == 3
    assert compute_affected_count(object(), {1, 2}) == 2
    assert compute_affected_count(object(), object()) == 0

    assert (
        classify_irreversibility(SimpleNamespace(irreversibility="irreversible"))
        == "irreversible"
    )
    assert classify_irreversibility(SimpleNamespace(deletes_data=True)) == "irreversible"
    assert (
        classify_irreversibility(SimpleNamespace(external_side_effects=True))
        == "partially_reversible"
    )
    assert classify_irreversibility(object()) == "reversible"

    assert estimate_duration(SimpleNamespace(estimated_seconds="5")).total_seconds() == 5
    assert estimate_duration(SimpleNamespace(affected_count=100)).total_seconds() == 4

    preview = build_change_preview(
        SimpleNamespace(affected_count=2, cascade_implications=["sessions revoked"]),
        [],
    )
    assert preview.affected_count == 2
    assert preview.cascade_implications == ["sessions revoked"]


def _bundle(config: dict[str, Any], *, signing: _Signing | None = None) -> bytes:
    config_bytes = yaml.safe_dump(config, sort_keys=True).encode("utf-8")
    manifest = {
        "hashes": {"config.yaml": hashlib.sha256(config_bytes).hexdigest()},
        "source_public_key_hex": "public-key",
    }
    manifest_bytes = json.dumps(manifest).encode("utf-8")
    signature = signing.sign(manifest_bytes) if signing is not None else b"signature"
    return _tar_bundle(
        {
            "config.yaml": config_bytes,
            "manifest.json": manifest_bytes,
            "signature.bin": signature,
        }
    )


@pytest.mark.asyncio
async def test_config_export_import_round_trip_and_audit(auth_settings: PlatformSettings) -> None:
    audit_chain = _AuditChain()
    tenant_id = uuid4()

    bundle, bundle_hash = await ConfigExportService(auth_settings, audit_chain).export_config(
        "tenant",
        tenant_id=tenant_id,
    )
    extracted = _extract_bundle(bundle)
    manifest = json.loads(extracted["manifest.json"].decode("utf-8"))
    preview = await ConfigImportService(audit_chain).preview_import(bundle)
    result = await ConfigImportService(audit_chain).apply_import(
        bundle,
        "IMPORT CONFIG",
        _actor(),
    )

    assert manifest["scope"] == "tenant"
    assert manifest["tenant_id"] == str(tenant_id)
    assert bundle_hash == hashlib.sha256(bundle).hexdigest()
    assert [diff.category for diff in preview.diffs] == sorted(
        _redacted_config("tenant", tenant_id)
    )
    assert result.applied is True
    assert result.changed_count == len(preview.diffs)
    assert audit_chain.appended[-1]["event_type"] == "platform.config.imported"


@pytest.mark.asyncio
async def test_config_import_validation_errors() -> None:
    audit_chain = _AuditChain()
    good_bundle = _bundle({"settings": {"ok": True}}, signing=audit_chain.signing)

    with pytest.raises(ValueError, match="confirmation phrase"):
        await ConfigImportService(audit_chain).apply_import(good_bundle, "wrong", _actor())

    with pytest.raises(ValueError, match="missing required"):
        _extract_bundle(_tar_bundle({"config.yaml": b"settings: {}"}))

    bad_manifest = _tar_bundle(
        {
            "config.yaml": b"settings: {}",
            "manifest.json": b"[]",
            "signature.bin": b"signature",
        }
    )
    with pytest.raises(ValueError, match="manifest is invalid"):
        await ConfigImportService(audit_chain).preview_import(bad_manifest)

    bad_hash = _tar_bundle(
        {
            "config.yaml": b"settings: {}",
            "manifest.json": json.dumps(
                {"hashes": {"config.yaml": "wrong"}, "source_public_key_hex": "public-key"}
            ).encode("utf-8"),
            "signature.bin": b"signature",
        }
    )
    with pytest.raises(ValueError, match="hash does not match"):
        await ConfigImportService(audit_chain).preview_import(bad_hash)

    untrusted = _AuditChain(verify_result=False)
    with pytest.raises(ValueError, match="signature does not verify"):
        await ConfigImportService(untrusted).preview_import(
            _bundle({"settings": {}}, signing=untrusted.signing)
        )


def test_admin_response_helpers_handle_tenant_and_payloads() -> None:
    tenant_id = uuid4()

    assert tenant_id_from_user({"tenant_id": str(tenant_id)}) == tenant_id
    assert tenant_id_from_user({"tenant_id": "not-a-uuid"}) is None
    assert tenant_id_from_user({}) is None
    assert empty_list("users", {"tenant_id": str(tenant_id)}).tenant_id == tenant_id
    assert empty_detail("users", "user-1").id == "user-1"

    response = accepted(
        "delete",
        "users/user-1",
        preview=True,
        affected_count=1,
        message="accepted",
        bulk_action_id=uuid4(),
        change_preview={"irreversibility": "reversible"},
    )

    assert response.accepted is True
    assert response.preview is True
    assert response.change_preview == {"irreversibility": "reversible"}
    assert set(FEATURE_FLAG_DEFAULTS) >= {"FEATURE_IMPERSONATION_ENABLED"}
