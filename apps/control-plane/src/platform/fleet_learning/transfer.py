from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext
from platform.common.exceptions import ValidationError
from platform.fleet_learning.events import publish_transfer_status_changed
from platform.fleet_learning.exceptions import IncompatibleTopologyError, TransferError
from platform.fleet_learning.models import CrossFleetTransferRequest, TransferRequestStatus
from platform.fleet_learning.repository import CrossFleetTransferRepository
from platform.fleet_learning.schemas import (
    CrossFleetTransferCreate,
    CrossFleetTransferResponse,
    TransferRejectRequest,
)
from platform.fleets.events import FleetTransferStatusChangedPayload
from platform.fleets.models import FleetTopologyType
from platform.fleets.repository import (
    FleetOrchestrationRulesRepository,
    FleetTopologyVersionRepository,
)
from platform.fleets.schemas import FleetOrchestrationRulesCreate
from typing import Any, Literal, cast
from uuid import UUID, uuid4

TRANSFER_PATTERN_BUCKET = "fleet-patterns"
MAX_INLINE_PATTERN_BYTES = 50 * 1024


class CrossFleetTransferService:
    def __init__(
        self,
        *,
        repository: CrossFleetTransferRepository,
        rules_repo: FleetOrchestrationRulesRepository,
        topology_repo: FleetTopologyVersionRepository,
        object_storage: Any,
        fleet_service: Any,
        producer: Any | None,
    ) -> None:
        self.repository = repository
        self.rules_repo = rules_repo
        self.topology_repo = topology_repo
        self.object_storage = object_storage
        self.fleet_service = fleet_service
        self.producer = producer

    async def propose(
        self,
        source_fleet_id: UUID,
        workspace_id: UUID,
        request: CrossFleetTransferCreate,
        proposed_by: UUID,
    ) -> CrossFleetTransferResponse:
        if source_fleet_id == request.target_fleet_id:
            raise ValidationError(
                "FLEET_TRANSFER_SELF_TARGET",
                "source_fleet_id and target_fleet_id must differ",
            )
        await self.fleet_service.get_fleet(request.target_fleet_id, workspace_id)
        pattern_definition: dict[str, Any] | None = dict(request.pattern_definition)
        pattern_minio_key: str | None = None
        request_id = uuid4()
        payload_bytes = json.dumps(request.pattern_definition).encode("utf-8")
        if len(payload_bytes) > MAX_INLINE_PATTERN_BYTES:
            pattern_minio_key = f"{TRANSFER_PATTERN_BUCKET}/{request_id}/pattern.json"
            await self.object_storage.create_bucket_if_not_exists(TRANSFER_PATTERN_BUCKET)
            await self.object_storage.put_object(
                TRANSFER_PATTERN_BUCKET,
                f"{request_id}/pattern.json",
                payload_bytes,
                content_type="application/json",
            )
            pattern_definition = {
                "metadata": {
                    "description": request.pattern_definition.get("description"),
                    "orchestration_rules_version": request.pattern_definition.get(
                        "orchestration_rules_version"
                    ),
                }
            }
        transfer = await self.repository.create(
            CrossFleetTransferRequest(
                id=request_id,
                workspace_id=workspace_id,
                source_fleet_id=source_fleet_id,
                target_fleet_id=request.target_fleet_id,
                status=TransferRequestStatus.proposed,
                pattern_definition=pattern_definition,
                pattern_minio_key=pattern_minio_key,
                proposed_by=proposed_by,
            )
        )
        await self._publish_status_changed(transfer)
        return CrossFleetTransferResponse.model_validate(transfer)

    async def approve(
        self,
        transfer_id: UUID,
        workspace_id: UUID,
        approved_by: UUID,
    ) -> CrossFleetTransferResponse:
        transfer = await self._require_transfer(transfer_id, workspace_id)
        if transfer.status is not TransferRequestStatus.proposed:
            raise TransferError("Only proposed transfers can be approved")
        transfer.status = TransferRequestStatus.approved
        transfer.approved_by = approved_by
        await self.repository.update_status(transfer)
        await self._publish_status_changed(transfer)
        return CrossFleetTransferResponse.model_validate(transfer)

    async def reject(
        self,
        transfer_id: UUID,
        workspace_id: UUID,
        request: TransferRejectRequest,
    ) -> CrossFleetTransferResponse:
        transfer = await self._require_transfer(transfer_id, workspace_id)
        if transfer.status is not TransferRequestStatus.proposed:
            raise TransferError("Only proposed transfers can be rejected")
        transfer.status = TransferRequestStatus.rejected
        transfer.rejected_reason = request.reason
        await self.repository.update_status(transfer)
        await self._publish_status_changed(transfer)
        return CrossFleetTransferResponse.model_validate(transfer)

    async def apply(self, transfer_id: UUID, workspace_id: UUID) -> CrossFleetTransferResponse:
        transfer = await self._require_transfer(transfer_id, workspace_id)
        if transfer.status is not TransferRequestStatus.approved:
            raise TransferError("Only approved transfers can be applied")
        pattern = await self._load_pattern(transfer)
        rules_snapshot = pattern.get("rules_snapshot") or pattern
        target_topology = await self.topology_repo.get_current(transfer.target_fleet_id)
        if target_topology is None:
            raise TransferError("Target fleet topology was not found")
        current_rules = await self.fleet_service.get_orchestration_rules(
            transfer.target_fleet_id,
            workspace_id,
        )
        adapted_rules = self._adapt_pattern(
            pattern,
            rules_snapshot,
            target_topology.config,
            target_topology.topology_type,
            transfer.id,
        )
        updated = await self.fleet_service.update_orchestration_rules(
            transfer.target_fleet_id,
            workspace_id,
            FleetOrchestrationRulesCreate.model_validate(adapted_rules),
        )
        metadata = dict(transfer.pattern_definition or {})
        nested_metadata = cast(dict[str, Any], metadata.setdefault("metadata", {}))
        nested_metadata["target_before_rules_version"] = current_rules.version
        nested_metadata["target_after_rules_version"] = updated.version
        transfer.pattern_definition = metadata
        transfer.status = TransferRequestStatus.applied
        transfer.applied_at = datetime.now(UTC)
        await self.repository.update_status(transfer)
        await self._publish_status_changed(transfer)
        return CrossFleetTransferResponse.model_validate(transfer)

    async def revert(self, transfer_id: UUID, workspace_id: UUID) -> CrossFleetTransferResponse:
        transfer = await self._require_transfer(transfer_id, workspace_id)
        if transfer.status is not TransferRequestStatus.applied:
            raise TransferError("Only applied transfers can be reverted")
        metadata = cast(
            dict[str, Any],
            dict(transfer.pattern_definition or {}).get("metadata", {}),
        )
        before_version = metadata.get("target_before_rules_version")
        if before_version is None:
            raise TransferError("Transfer is missing original orchestration rules version metadata")
        restored = await self.rules_repo.set_current_version(
            transfer.target_fleet_id, int(before_version)
        )
        if restored is None:
            raise TransferError("Original orchestration rules version was not found")
        transfer.reverted_at = datetime.now(UTC)
        await self.repository.update_status(transfer)
        await self._publish_status_changed(transfer)
        return CrossFleetTransferResponse.model_validate(transfer)

    async def list_for_fleet(
        self,
        fleet_id: UUID,
        workspace_id: UUID,
        *,
        role: Literal["source", "target"] | None = None,
        status: TransferRequestStatus | None = None,
    ) -> list[CrossFleetTransferResponse]:
        return [
            CrossFleetTransferResponse.model_validate(item)
            for item in await self.repository.list_for_fleet(fleet_id, role=role, status=status)
            if item.workspace_id == workspace_id
        ]

    async def get(self, transfer_id: UUID, workspace_id: UUID) -> CrossFleetTransferResponse:
        return CrossFleetTransferResponse.model_validate(
            await self._require_transfer(transfer_id, workspace_id)
        )

    async def _require_transfer(
        self, transfer_id: UUID, workspace_id: UUID
    ) -> CrossFleetTransferRequest:
        transfer = await self.repository.get_by_id(transfer_id)
        if transfer is None or transfer.workspace_id != workspace_id:
            raise TransferError("Transfer request was not found", code="FLEET_TRANSFER_NOT_FOUND")
        return transfer

    async def _load_pattern(self, transfer: CrossFleetTransferRequest) -> dict[str, Any]:
        if transfer.pattern_definition is not None and transfer.pattern_minio_key is None:
            return dict(transfer.pattern_definition)
        if transfer.pattern_minio_key is None:
            return {}
        key = transfer.pattern_minio_key.split("/", 1)[1]
        raw = await self.object_storage.get_object(TRANSFER_PATTERN_BUCKET, key)
        loaded = json.loads(raw.decode("utf-8"))
        if isinstance(loaded, dict):
            return cast(dict[str, Any], loaded)
        raise TransferError("Stored transfer pattern payload must be a JSON object")

    @staticmethod
    def _adapt_pattern(
        pattern: dict[str, Any],
        rules_snapshot: dict[str, Any],
        topology_config: dict[str, Any],
        topology_type: FleetTopologyType,
        transfer_id: UUID,
    ) -> dict[str, Any]:
        adapted = dict(rules_snapshot)
        if topology_type is FleetTopologyType.hierarchical:
            lead_fqn = str(topology_config.get("lead_fqn", "")).strip()
            if not lead_fqn:
                raise IncompatibleTopologyError(transfer_id, "hierarchical target lacks lead_fqn")
            adapted.setdefault("delegation", {})
            adapted["delegation"] = dict(adapted["delegation"])
            adapted["delegation"].setdefault("config", {})
            adapted["delegation"]["config"]["lead_fqn"] = lead_fqn
        elif topology_type is FleetTopologyType.peer_to_peer:
            if "delegation" in adapted and isinstance(adapted["delegation"], dict):
                delegation = dict(adapted["delegation"])
                config = dict(delegation.get("config", {}))
                config.pop("lead_fqn", None)
                delegation["config"] = config
                adapted["delegation"] = delegation
        return adapted

    async def _publish_status_changed(self, transfer: CrossFleetTransferRequest) -> None:
        await publish_transfer_status_changed(
            self.producer,
            FleetTransferStatusChangedPayload(
                transfer_id=transfer.id,
                workspace_id=transfer.workspace_id,
                source_fleet_id=transfer.source_fleet_id,
                target_fleet_id=transfer.target_fleet_id,
                status=transfer.status.value,
            ),
            CorrelationContext(
                workspace_id=transfer.workspace_id,
                fleet_id=transfer.source_fleet_id,
                correlation_id=uuid4(),
            ),
        )
