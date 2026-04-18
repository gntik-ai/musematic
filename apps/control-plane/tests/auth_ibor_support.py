from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from platform.auth.models import (
    IBORConnector,
    IBORSourceType,
    IBORSyncMode,
    IBORSyncRun,
    IBORSyncRunStatus,
    UserRole,
)


class _ScalarsResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)


class _ExecuteResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> _ScalarsResult:
        return _ScalarsResult(self._rows)


@dataclass
class FakeDB:
    agents: list[Any] = field(default_factory=list)

    async def execute(self, statement: Any) -> _ExecuteResult:
        rows = list(self.agents)
        criteria = list(getattr(statement, '_where_criteria', ()) or ())
        allowed_statuses: set[str] | None = None
        for criterion in criteria:
            right = getattr(criterion, 'right', None)
            values = None
            if hasattr(right, 'value') and getattr(right, 'value') is not None:
                values = getattr(right, 'value')
            elif hasattr(right, 'effective_value') and getattr(right, 'effective_value') is not None:
                values = getattr(right, 'effective_value')
            if isinstance(values, (list, tuple, set)):
                allowed_statuses = {str(value) for value in values}
                break
        if allowed_statuses is not None:
            rows = [row for row in rows if str(getattr(row, 'status', '')) in allowed_statuses]
        return _ExecuteResult(rows)


class SCIMCollector:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def post_user(self, payload: dict[str, Any]) -> None:
        self.calls.append(dict(payload))


@dataclass
class InMemoryAccountsRepository:
    users_by_email: dict[str, Any] = field(default_factory=dict)

    async def get_user_by_email(self, email: str) -> Any | None:
        return self.users_by_email.get(email.lower())

    async def create_user(
        self,
        email: str,
        display_name: str,
        status: Any,
        signup_source: Any,
        invitation_id: UUID | None = None,
    ) -> Any:
        del invitation_id
        user = SimpleNamespace(
            id=uuid4(),
            email=email.lower(),
            display_name=display_name,
            status=status,
            signup_source=signup_source,
        )
        self.users_by_email[user.email] = user
        return user


@dataclass
class InMemoryIBORRepository:
    connectors: dict[UUID, IBORConnector] = field(default_factory=dict)
    sync_runs: dict[UUID, IBORSyncRun] = field(default_factory=dict)
    user_roles: list[UserRole] = field(default_factory=list)
    platform_users_by_email: dict[str, Any] = field(default_factory=dict)
    db: FakeDB = field(default_factory=FakeDB)

    async def get_connector_by_name(self, name: str) -> IBORConnector | None:
        for connector in self.connectors.values():
            if connector.name == name:
                return connector
        return None

    async def create_connector(
        self,
        *,
        name: str,
        source_type: IBORSourceType,
        sync_mode: IBORSyncMode,
        cadence_seconds: int,
        credential_ref: str,
        role_mapping_policy: list[dict[str, Any]],
        enabled: bool,
        created_by: UUID,
    ) -> IBORConnector:
        connector = IBORConnector(
            name=name,
            source_type=source_type,
            sync_mode=sync_mode,
            cadence_seconds=cadence_seconds,
            credential_ref=credential_ref,
            role_mapping_policy=role_mapping_policy,
            enabled=enabled,
            created_by=created_by,
        )
        connector.id = uuid4()
        connector.created_at = datetime.now(UTC)
        connector.updated_at = connector.created_at
        connector.last_run_at = None
        connector.last_run_status = None
        self.connectors[connector.id] = connector
        return connector

    async def list_connectors(self) -> list[IBORConnector]:
        return sorted(self.connectors.values(), key=lambda item: (item.name, item.id))

    async def list_enabled_connectors(self) -> list[IBORConnector]:
        return [item for item in await self.list_connectors() if item.enabled]

    async def get_connector(self, connector_id: UUID) -> IBORConnector | None:
        return self.connectors.get(connector_id)

    async def update_connector(self, connector: IBORConnector, **fields: Any) -> IBORConnector:
        for key, value in fields.items():
            setattr(connector, key, value)
        connector.updated_at = datetime.now(UTC)
        return connector

    async def soft_delete_connector(self, connector: IBORConnector) -> IBORConnector:
        connector.enabled = False
        connector.updated_at = datetime.now(UTC)
        return connector

    async def create_sync_run(
        self,
        *,
        connector_id: UUID,
        mode: IBORSyncMode,
        status: IBORSyncRunStatus,
        counts: dict[str, int] | None = None,
        error_details: list[dict[str, Any]] | None = None,
        triggered_by: UUID | None,
    ) -> IBORSyncRun:
        run = IBORSyncRun(
            connector_id=connector_id,
            mode=mode,
            status=status,
            counts=counts or {},
            error_details=error_details or [],
            triggered_by=triggered_by,
        )
        run.id = uuid4()
        run.started_at = datetime.now(UTC)
        run.finished_at = None
        self.sync_runs[run.id] = run
        return run

    async def get_sync_run(self, run_id: UUID) -> IBORSyncRun | None:
        return self.sync_runs.get(run_id)

    async def update_sync_run(
        self,
        run: IBORSyncRun,
        *,
        status: IBORSyncRunStatus,
        counts: dict[str, int],
        error_details: list[dict[str, Any]],
        finished_at: datetime | None = None,
    ) -> IBORSyncRun:
        run.status = status
        run.counts = counts
        run.error_details = error_details
        run.finished_at = finished_at or datetime.now(UTC)
        return run

    async def touch_connector_run(
        self,
        connector: IBORConnector,
        *,
        status: str,
        last_run_at: datetime | None = None,
    ) -> None:
        connector.last_run_status = status
        connector.last_run_at = last_run_at or datetime.now(UTC)
        connector.updated_at = datetime.now(UTC)

    async def list_sync_runs(
        self,
        connector_id: UUID,
        *,
        limit: int,
        cursor: str | None = None,
    ) -> tuple[list[IBORSyncRun], str | None]:
        rows = [row for row in self.sync_runs.values() if row.connector_id == connector_id]
        rows.sort(key=lambda row: (row.started_at, row.id), reverse=True)
        if cursor is not None:
            started_at, run_id = self._decode_run_cursor(cursor)
            rows = [
                row
                for row in rows
                if row.started_at < started_at or (row.started_at == started_at and row.id < run_id)
            ]
        next_cursor = None
        page = rows[: limit + 1]
        if len(page) > limit:
            page = page[:limit]
            cursor_row = page[-1]
            next_cursor = self._encode_run_cursor(cursor_row.started_at, cursor_row.id)
        return page, next_cursor

    @staticmethod
    def _encode_run_cursor(started_at: datetime, run_id: UUID) -> str:
        raw = f"{started_at.isoformat()}|{run_id}"
        return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")

    @staticmethod
    def _decode_run_cursor(cursor: str) -> tuple[datetime, UUID]:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        started_at_raw, run_id_raw = raw.split("|", 1)
        return datetime.fromisoformat(started_at_raw), UUID(run_id_raw)

    async def list_user_roles(
        self,
        *,
        user_id: UUID | None = None,
        user_email: str | None = None,
    ) -> list[UserRole]:
        if user_id is None and user_email is None:
            raise ValueError("user_id or user_email is required")
        resolved_user_id = user_id
        if resolved_user_id is None:
            user = self.platform_users_by_email.get(str(user_email).lower())
            if user is None:
                return []
            resolved_user_id = user.id
        return [row for row in self.user_roles if row.user_id == resolved_user_id]

    async def get_user_roles(self, user_id: UUID, workspace_id: UUID | None) -> list[UserRole]:
        rows = [row for row in self.user_roles if row.user_id == user_id]
        if workspace_id is None:
            return rows
        return [
            row for row in rows if row.workspace_id is None or row.workspace_id == workspace_id
        ]

    async def get_user_roles_by_source_connector(
        self,
        user_id: UUID,
        source_connector_id: UUID,
    ) -> list[UserRole]:
        return [
            row
            for row in self.user_roles
            if row.user_id == user_id and row.source_connector_id == source_connector_id
        ]

    async def assign_user_role(
        self,
        user_id: UUID,
        role: str,
        workspace_id: UUID | None,
        source_connector_id: UUID | None = None,
    ) -> UserRole:
        for row in self.user_roles:
            if row.user_id == user_id and row.role == role and row.workspace_id == workspace_id:
                if row.source_connector_id is None:
                    return row
                if source_connector_id is None:
                    row.source_connector_id = None
                elif row.source_connector_id != source_connector_id:
                    row.source_connector_id = source_connector_id
                return row
        assignment = UserRole(
            user_id=user_id,
            role=role,
            workspace_id=workspace_id,
            source_connector_id=source_connector_id,
        )
        assignment.id = uuid4()
        assignment.created_at = datetime.now(UTC)
        assignment.updated_at = assignment.created_at
        self.user_roles.append(assignment)
        return assignment

    async def revoke_user_role(self, user_role_id: UUID) -> None:
        self.user_roles = [row for row in self.user_roles if row.id != user_role_id]

    async def list_user_roles_by_connector(self, connector_id: UUID) -> list[UserRole]:
        return [row for row in self.user_roles if row.source_connector_id == connector_id]

    async def get_platform_user_by_email(self, email: str) -> Any | None:
        return self.platform_users_by_email.get(email.lower())

    async def create_platform_user(self, user_id: UUID, email: str, display_name: str) -> Any:
        user = SimpleNamespace(
            id=user_id,
            email=email.lower(),
            display_name=display_name,
            status="active",
        )
        self.platform_users_by_email[user.email] = user
        return user
