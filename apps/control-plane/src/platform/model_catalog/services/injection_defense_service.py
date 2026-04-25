from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from platform.common.exceptions import AuthorizationError, NotFoundError
from platform.model_catalog.models import InjectionDefensePattern
from platform.model_catalog.repository import ModelCatalogRepository
from platform.model_catalog.schemas import (
    InjectionFindingResponse,
    InjectionPatternCreate,
    InjectionPatternListResponse,
    InjectionPatternPatch,
    InjectionPatternResponse,
)
from typing import ClassVar
from uuid import UUID


@dataclass(frozen=True, slots=True)
class InjectionFindingRecord:
    layer: str
    pattern_name: str
    severity: str
    action_taken: str
    workspace_id: UUID
    agent_id: UUID | None
    created_at: datetime


class InjectionDefenseService:
    _findings: ClassVar[list[InjectionFindingRecord]] = []

    def __init__(self, repository: ModelCatalogRepository) -> None:
        self.repository = repository

    async def create_pattern(self, request: InjectionPatternCreate) -> InjectionPatternResponse:
        pattern = await self.repository.add(InjectionDefensePattern(**request.model_dump()))
        return InjectionPatternResponse.model_validate(pattern)

    async def list_patterns(
        self,
        *,
        layer: str | None = None,
        workspace_id: UUID | None = None,
    ) -> InjectionPatternListResponse:
        items = await self.repository.list_injection_patterns(
            layer=layer,
            workspace_id=workspace_id,
        )
        return InjectionPatternListResponse(
            items=[InjectionPatternResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def update_pattern(
        self,
        pattern_id: UUID,
        patch: InjectionPatternPatch,
    ) -> InjectionPatternResponse:
        pattern = await self._get(pattern_id)
        updates = patch.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(pattern, field, value)
        if updates:
            await self.repository.session.flush()
        return InjectionPatternResponse.model_validate(pattern)

    async def delete_pattern(self, pattern_id: UUID) -> None:
        pattern = await self._get(pattern_id)
        if pattern.seeded:
            raise AuthorizationError(
                "SEEDED_INJECTION_PATTERN_IMMUTABLE",
                "Seeded injection patterns cannot be deleted.",
            )
        await self.repository.delete_injection_pattern(pattern)

    def record_finding(
        self,
        *,
        layer: str,
        pattern_name: str,
        severity: str,
        action_taken: str,
        workspace_id: UUID,
        agent_id: UUID | None = None,
    ) -> InjectionFindingResponse:
        record = InjectionFindingRecord(
            layer=layer,
            pattern_name=pattern_name,
            severity=severity,
            action_taken=action_taken,
            workspace_id=workspace_id,
            agent_id=agent_id,
            created_at=datetime.now(UTC),
        )
        self._findings.append(record)
        return InjectionFindingResponse(**asdict(record))

    def list_findings(
        self,
        *,
        workspace_id: UUID | None = None,
        layer: str | None = None,
    ) -> list[InjectionFindingResponse]:
        items = self._findings
        if workspace_id is not None:
            items = [item for item in items if item.workspace_id == workspace_id]
        if layer is not None:
            items = [item for item in items if item.layer == layer]
        return [InjectionFindingResponse(**asdict(item)) for item in items]

    async def _get(self, pattern_id: UUID) -> InjectionDefensePattern:
        pattern = await self.repository.get_injection_pattern(pattern_id)
        if pattern is None:
            raise NotFoundError("INJECTION_PATTERN_NOT_FOUND", "Injection pattern not found")
        return pattern
