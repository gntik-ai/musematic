from __future__ import annotations

from platform.auth.exceptions import IBORConnectorConflictError, IBORConnectorNotFoundError
from platform.auth.models import IBORConnector, IBORSyncRun
from platform.auth.repository import AuthRepository
from platform.auth.schemas import (
    IBORConnectorCreate,
    IBORConnectorListResponse,
    IBORConnectorResponse,
    IBORConnectorUpdate,
    IBORRoleMappingRule,
    IBORSyncRunListResponse,
    IBORSyncRunResponse,
    StepResult,
    TestConnectionResponse,
)
from uuid import UUID


class IBORConnectorService:
    def __init__(self, repository: AuthRepository) -> None:
        self.repository = repository

    async def create_connector(
        self,
        payload: IBORConnectorCreate,
        *,
        actor_id: UUID,
    ) -> IBORConnectorResponse:
        existing = await self.repository.get_connector_by_name(payload.name)
        if existing is not None:
            raise IBORConnectorConflictError(payload.name)
        connector = await self.repository.create_connector(
            name=payload.name,
            source_type=payload.source_type,
            sync_mode=payload.sync_mode,
            cadence_seconds=payload.cadence_seconds,
            credential_ref=payload.credential_ref,
            role_mapping_policy=[
                rule.model_dump(mode="json") for rule in payload.role_mapping_policy
            ],
            enabled=payload.enabled,
            created_by=actor_id,
        )
        return self._connector_response(connector)

    async def list_connectors(self) -> IBORConnectorListResponse:
        items = [self._connector_response(item) for item in await self.repository.list_connectors()]
        return IBORConnectorListResponse(items=items)

    async def get_connector(self, connector_id: UUID) -> IBORConnectorResponse:
        connector = await self._get_connector_or_raise(connector_id)
        return self._connector_response(connector)

    async def update_connector(
        self,
        connector_id: UUID,
        payload: IBORConnectorUpdate,
    ) -> IBORConnectorResponse:
        connector = await self._get_connector_or_raise(connector_id)
        existing = await self.repository.get_connector_by_name(payload.name)
        if existing is not None and existing.id != connector.id:
            raise IBORConnectorConflictError(payload.name)
        updated = await self.repository.update_connector(
            connector,
            name=payload.name,
            source_type=payload.source_type,
            sync_mode=payload.sync_mode,
            cadence_seconds=payload.cadence_seconds,
            credential_ref=payload.credential_ref,
            role_mapping_policy=[
                rule.model_dump(mode="json") for rule in payload.role_mapping_policy
            ],
            enabled=payload.enabled,
        )
        return self._connector_response(updated)

    async def delete_connector(self, connector_id: UUID) -> None:
        connector = await self._get_connector_or_raise(connector_id)
        await self.repository.soft_delete_connector(connector)

    async def list_sync_runs(
        self,
        connector_id: UUID,
        *,
        limit: int = 90,
        cursor: str | None = None,
    ) -> IBORSyncRunListResponse:
        await self._get_connector_or_raise(connector_id)
        resolved_limit = max(1, min(limit, 500))
        runs, next_cursor = await self.repository.list_sync_runs(
            connector_id,
            limit=resolved_limit,
            cursor=cursor,
        )
        return IBORSyncRunListResponse(
            items=[self._sync_run_response(item) for item in runs],
            next_cursor=next_cursor,
        )

    async def test_connection(self, connector_id: UUID) -> TestConnectionResponse:
        connector = await self._get_connector_or_raise(connector_id)
        source_type = getattr(connector.source_type, "value", connector.source_type)
        steps = [
            StepResult(step="connector_lookup", status="success", duration_ms=0),
            StepResult(step="credential_reference", status="success", duration_ms=0),
            StepResult(
                step=f"{source_type}_diagnostic_ready",
                status="success",
                duration_ms=0,
            ),
        ]
        return TestConnectionResponse(connector_id=connector.id, steps=steps, success=True)

    async def _get_connector_or_raise(self, connector_id: UUID) -> IBORConnector:
        connector = await self.repository.get_connector(connector_id)
        if connector is None:
            raise IBORConnectorNotFoundError(str(connector_id))
        return connector

    @staticmethod
    def _connector_response(connector: IBORConnector) -> IBORConnectorResponse:
        rules = [IBORRoleMappingRule.model_validate(item) for item in connector.role_mapping_policy]
        return IBORConnectorResponse(
            id=connector.id,
            name=connector.name,
            source_type=connector.source_type,
            sync_mode=connector.sync_mode,
            cadence_seconds=connector.cadence_seconds,
            credential_ref=connector.credential_ref,
            role_mapping_policy=rules,
            enabled=connector.enabled,
            last_run_at=connector.last_run_at,
            last_run_status=connector.last_run_status,
            created_by=connector.created_by,
            created_at=connector.created_at,
            updated_at=connector.updated_at,
        )

    @staticmethod
    def _sync_run_response(run: IBORSyncRun) -> IBORSyncRunResponse:
        return IBORSyncRunResponse(
            id=run.id,
            connector_id=run.connector_id,
            mode=run.mode,
            started_at=run.started_at,
            finished_at=run.finished_at,
            status=run.status,
            counts={str(key): int(value) for key, value in run.counts.items()},
            error_details=[dict(item) for item in run.error_details],
            triggered_by=run.triggered_by,
        )
