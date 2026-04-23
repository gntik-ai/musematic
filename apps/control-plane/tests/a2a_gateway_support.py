from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from platform.a2a_gateway.models import (
    A2AAuditRecord,
    A2ADirection,
    A2AExternalEndpoint,
    A2ATask,
    A2ATaskState,
)
from platform.common.clients.redis import RateLimitResult
from platform.common.config import PlatformSettings
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4


class ScalarSequenceStub:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def all(self) -> list[Any]:
        return list(self._items)


class ExecuteResultStub:
    def __init__(self, *, scalar: Any | None = None, items: list[Any] | None = None) -> None:
        self._scalar = scalar
        self._items = items or []

    def scalar_one_or_none(self) -> Any | None:
        return self._scalar

    def scalars(self) -> ScalarSequenceStub:
        return ScalarSequenceStub(self._items)


class SessionStub:
    def __init__(self, *, execute_results: list[ExecuteResultStub] | None = None) -> None:
        self.execute_results = list(execute_results or [])
        self.added: list[Any] = []
        self.flush_count = 0

    def add(self, item: Any) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flush_count += 1

    async def execute(self, statement: Any) -> ExecuteResultStub:
        del statement
        if not self.execute_results:
            raise AssertionError("Unexpected execute call")
        return self.execute_results.pop(0)


@dataclass
class DecisionStub:
    allowed: bool = True
    block_reason: str | None = None
    policy_rule_ref: dict[str, Any] | None = None

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        del mode
        return {
            "allowed": self.allowed,
            "block_reason": self.block_reason,
            "policy_rule_ref": self.policy_rule_ref,
        }


@dataclass
class SanitizationStub:
    output: str
    redaction_count: int = 0
    redacted_types: list[str] = field(default_factory=list)


class ToolGatewayStub:
    def __init__(
        self,
        *,
        validate_result: DecisionStub | None = None,
        sanitize_result: SanitizationStub | None = None,
    ) -> None:
        self.validate_result = validate_result or DecisionStub()
        self.sanitize_result = sanitize_result or SanitizationStub(output="ok")
        self.validate_calls: list[dict[str, Any]] = []
        self.sanitize_calls: list[dict[str, Any]] = []

    async def validate_tool_invocation(self, **kwargs: Any) -> DecisionStub:
        self.validate_calls.append(kwargs)
        return self.validate_result

    async def sanitize_tool_output(self, text: str, **kwargs: Any) -> SanitizationStub:
        self.sanitize_calls.append({"text": text, **kwargs})
        return self.sanitize_result


class AuthServiceStub:
    def __init__(self, principal: dict[str, Any] | Exception | None = None) -> None:
        self.principal = principal or {"sub": str(uuid4())}

    async def validate_token(self, token: str) -> dict[str, Any]:
        del token
        if isinstance(self.principal, Exception):
            raise self.principal
        return self.principal


class FakeRedisClient:
    def __init__(
        self,
        *,
        rate_limit_results: list[RateLimitResult] | None = None,
        store: dict[str, Any] | None = None,
    ) -> None:
        self.rate_limit_results = list(
            rate_limit_results or [RateLimitResult(allowed=True, remaining=59, retry_after_ms=0)]
        )
        self.store = dict(store or {})
        self.check_calls: list[dict[str, Any]] = []

    async def check_rate_limit(
        self,
        resource: str,
        key: str,
        limit: int,
        window_ms: int,
    ) -> RateLimitResult:
        self.check_calls.append(
            {
                "resource": resource,
                "key": key,
                "limit": limit,
                "window_ms": window_ms,
            }
        )
        if self.rate_limit_results:
            return self.rate_limit_results.pop(0)
        return RateLimitResult(allowed=True, remaining=max(limit - 1, 0), retry_after_ms=0)

    async def get(self, key: str) -> Any:
        return self.store.get(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        del ttl
        self.store[key] = value

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


class RecordingEventPublisher:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(self, **kwargs: Any) -> None:
        self.events.append(kwargs)


class InteractionRepositoryStub:
    def __init__(self) -> None:
        self.conversations: list[dict[str, Any]] = []
        self.interactions: dict[UUID, Any] = {}
        self.messages: list[dict[str, Any]] = []

    async def create_conversation(self, **kwargs: Any) -> Any:
        conversation_id = uuid4()
        payload = {"id": conversation_id, **kwargs}
        self.conversations.append(payload)
        return SimpleNamespace(**payload)

    async def create_interaction(self, **kwargs: Any) -> Any:
        interaction_id = uuid4()
        payload = {"id": interaction_id, **kwargs}
        interaction = SimpleNamespace(**payload)
        self.interactions[interaction_id] = interaction
        return interaction

    async def create_message(self, **kwargs: Any) -> Any:
        self.messages.append(kwargs)
        return SimpleNamespace(**kwargs)

    async def get_interaction(self, interaction_id: UUID, workspace_id: UUID) -> Any:
        del workspace_id
        return self.interactions.get(interaction_id)


class FakeA2ARepository:
    def __init__(self) -> None:
        self.tasks: dict[str, A2ATask] = {}
        self.endpoints: dict[UUID, A2AExternalEndpoint] = {}
        self.audits: list[A2AAuditRecord] = []
        self.policy_blocked: list[Any] = []
        self.session = SimpleNamespace()

    async def create_task(self, task: A2ATask) -> A2ATask:
        now = datetime.now(UTC)
        if getattr(task, "id", None) is None:
            task.id = uuid4()
        if getattr(task, "created_at", None) is None:
            task.created_at = now
        if getattr(task, "updated_at", None) is None:
            task.updated_at = now
        self.tasks[task.task_id] = task
        return task

    async def get_task_by_task_id(self, task_id: str) -> A2ATask | None:
        return self.tasks.get(task_id)

    async def get_task_by_id(self, task_db_id: UUID) -> A2ATask | None:
        return next((task for task in self.tasks.values() if task.id == task_db_id), None)

    async def update_task_state(self, task: A2ATask, **kwargs: Any) -> A2ATask:
        for key, value in kwargs.items():
            setattr(task, key, value)
        task.updated_at = datetime.now(UTC)
        return task

    async def create_external_endpoint(self, endpoint: A2AExternalEndpoint) -> A2AExternalEndpoint:
        now = datetime.now(UTC)
        if getattr(endpoint, "id", None) is None:
            endpoint.id = uuid4()
        if getattr(endpoint, "created_at", None) is None:
            endpoint.created_at = now
        if getattr(endpoint, "updated_at", None) is None:
            endpoint.updated_at = now
        if getattr(endpoint, "card_is_stale", None) is None:
            endpoint.card_is_stale = False
        if getattr(endpoint, "status", None) is None:
            endpoint.status = "active"
        self.endpoints[endpoint.id] = endpoint
        return endpoint

    async def get_external_endpoint(
        self,
        endpoint_id: UUID,
        *,
        workspace_id: UUID | None = None,
        include_deleted: bool = False,
    ) -> A2AExternalEndpoint | None:
        endpoint = self.endpoints.get(endpoint_id)
        if endpoint is None:
            return None
        if workspace_id is not None and endpoint.workspace_id != workspace_id:
            return None
        if not include_deleted and endpoint.status == "deleted":
            return None
        return endpoint

    async def list_external_endpoints(
        self,
        workspace_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> list[A2AExternalEndpoint]:
        items = [item for item in self.endpoints.values() if item.workspace_id == workspace_id]
        if not include_deleted:
            items = [item for item in items if item.status != "deleted"]
        return sorted(items, key=lambda item: (item.created_at, item.id))

    async def update_external_endpoint_cache(
        self,
        endpoint: A2AExternalEndpoint,
        **kwargs: Any,
    ) -> A2AExternalEndpoint:
        for key, value in kwargs.items():
            setattr(endpoint, key, value)
        endpoint.updated_at = datetime.now(UTC)
        return endpoint

    async def delete_external_endpoint(self, endpoint: A2AExternalEndpoint) -> A2AExternalEndpoint:
        endpoint.status = "deleted"
        endpoint.updated_at = datetime.now(UTC)
        return endpoint

    async def create_audit_record(self, record: A2AAuditRecord) -> A2AAuditRecord:
        self.audits.append(record)
        return record

    async def list_task_events(self, task_db_id: UUID) -> list[A2AAuditRecord]:
        return [record for record in self.audits if record.task_id == task_db_id]

    async def list_tasks_idle_expired(self, now: datetime | None = None) -> list[A2ATask]:
        reference = now or datetime.now(UTC)
        return [
            task
            for task in self.tasks.values()
            if task.a2a_state is A2ATaskState.input_required
            and task.idle_timeout_at is not None
            and task.idle_timeout_at < reference
        ]

    async def create_policy_blocked_record(self, record: Any) -> Any:
        self.policy_blocked.append(record)
        return record


def build_settings(**overrides: Any) -> PlatformSettings:
    base = {
        "AUTH_JWT_SECRET_KEY": "secret" * 6,
        "AUTH_JWT_ALGORITHM": "HS256",
    }
    base.update(overrides)
    return PlatformSettings(**base)


def build_principal(
    *,
    subject: UUID | None = None,
    workspace_id: UUID | None = None,
    roles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    principal: dict[str, Any] = {"sub": str(subject or uuid4())}
    if workspace_id is not None:
        principal["workspace_id"] = str(workspace_id)
    if roles is not None:
        principal["roles"] = roles
    return principal


def build_agent_profile(**overrides: Any) -> Any:
    workspace_id = overrides.pop("workspace_id", uuid4())
    return SimpleNamespace(
        id=overrides.pop("id", uuid4()),
        fqn=overrides.pop("fqn", "finance:verifier"),
        workspace_id=workspace_id,
        purpose=overrides.pop("purpose", "Verify financial evidence"),
        tags=overrides.pop("tags", ["finance", "verification"]),
        revisions=overrides.pop(
            "revisions",
            [SimpleNamespace(manifest_snapshot={"reasoning_modes": ["debate", "tot"]})],
        ),
        status=overrides.pop("status", "published"),
        deleted_at=overrides.pop("deleted_at", None),
        namespace=overrides.pop("namespace", None),
        **overrides,
    )


def build_task(**overrides: Any) -> A2ATask:
    now = datetime.now(UTC)
    task = A2ATask(
        task_id=overrides.pop("task_id", f"a2a-task-{uuid4().hex[:8]}"),
        direction=overrides.pop("direction", A2ADirection.inbound),
        a2a_state=overrides.pop("a2a_state", A2ATaskState.submitted),
        agent_fqn=overrides.pop("agent_fqn", "finance:verifier"),
        principal_id=overrides.pop("principal_id", uuid4()),
        workspace_id=overrides.pop("workspace_id", uuid4()),
        interaction_id=overrides.pop("interaction_id", uuid4()),
        conversation_id=overrides.pop("conversation_id", uuid4()),
        external_endpoint_id=overrides.pop("external_endpoint_id", None),
        protocol_version=overrides.pop("protocol_version", "1.0"),
        submitted_message=overrides.pop(
            "submitted_message",
            {"role": "user", "parts": [{"type": "text", "text": "do work"}]},
        ),
        result_payload=overrides.pop("result_payload", None),
        error_code=overrides.pop("error_code", None),
        error_message=overrides.pop("error_message", None),
        last_event_id=overrides.pop("last_event_id", None),
        idle_timeout_at=overrides.pop("idle_timeout_at", None),
        cancellation_requested_at=overrides.pop("cancellation_requested_at", None),
    )
    task.id = overrides.pop("id", uuid4())
    task.created_at = overrides.pop("created_at", now)
    task.updated_at = overrides.pop("updated_at", now)
    for key, value in overrides.items():
        setattr(task, key, value)
    return task


def build_endpoint(**overrides: Any) -> A2AExternalEndpoint:
    now = datetime.now(UTC)
    endpoint = A2AExternalEndpoint(
        workspace_id=overrides.pop("workspace_id", uuid4()),
        name=overrides.pop("name", "partner:agent"),
        endpoint_url=overrides.pop("endpoint_url", "https://partner.example.com/tasks"),
        agent_card_url=overrides.pop(
            "agent_card_url",
            "https://partner.example.com/.well-known/agent.json",
        ),
        auth_config=overrides.pop("auth_config", {"scheme": "bearer", "token": "secret"}),
        card_ttl_seconds=overrides.pop("card_ttl_seconds", 3600),
        cached_agent_card=overrides.pop("cached_agent_card", None),
        card_cached_at=overrides.pop("card_cached_at", None),
        card_is_stale=overrides.pop("card_is_stale", False),
        declared_version=overrides.pop("declared_version", None),
        status=overrides.pop("status", "active"),
        created_by=overrides.pop("created_by", uuid4()),
    )
    endpoint.id = overrides.pop("id", uuid4())
    endpoint.created_at = overrides.pop("created_at", now)
    endpoint.updated_at = overrides.pop("updated_at", now)
    for key, value in overrides.items():
        setattr(endpoint, key, value)
    return endpoint


def build_audit_record(**overrides: Any) -> A2AAuditRecord:
    record = A2AAuditRecord(
        task_id=overrides.pop("task_id", uuid4()),
        direction=overrides.pop("direction", A2ADirection.inbound),
        principal_id=overrides.pop("principal_id", uuid4()),
        agent_fqn=overrides.pop("agent_fqn", "finance:verifier"),
        action=overrides.pop("action", "task_submitted"),
        result=overrides.pop("result", "success"),
        policy_decision=overrides.pop("policy_decision", None),
        workspace_id=overrides.pop("workspace_id", uuid4()),
        error_code=overrides.pop("error_code", None),
    )
    record.id = overrides.pop("id", uuid4())
    record.occurred_at = overrides.pop("occurred_at", datetime.now(UTC))
    for key, value in overrides.items():
        setattr(record, key, value)
    return record


def expired_time(minutes: int = 5) -> datetime:
    return datetime.now(UTC) - timedelta(minutes=minutes)
