from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from platform.agentops.events import AgentOpsEventType, GovernanceEventPublisher
from platform.agentops.exceptions import RollbackIntegrityError, RollbackWindowExpiredError
from platform.agentops.models import AdaptationProposalStatus, SnapshotType
from platform.agentops.repository import AgentOpsRepository
from platform.agentops.schemas import AdaptationProposalResponse, AdaptationRollbackResponse
from platform.common.exceptions import NotFoundError, ValidationError
from typing import Any
from uuid import UUID


def utcnow() -> datetime:
    return datetime.now(UTC)


class AdaptationRollbackService:
    def __init__(
        self,
        *,
        repository: AgentOpsRepository,
        registry_service: Any,
        governance_publisher: GovernanceEventPublisher | None,
    ) -> None:
        self.repository = repository
        self.registry_service = registry_service
        self.governance_publisher = governance_publisher

    async def rollback(
        self,
        proposal_id: UUID,
        *,
        actor: UUID,
        reason: str,
    ) -> AdaptationRollbackResponse:
        proposal = await self.repository.get_adaptation(proposal_id)
        if proposal is None:
            raise NotFoundError("AGENTOPS_ADAPTATION_NOT_FOUND", "Adaptation proposal not found")
        if proposal.status != AdaptationProposalStatus.applied.value:
            raise ValidationError(
                "AGENTOPS_ADAPTATION_NOT_APPLIED",
                "Only applied proposals can be rolled back.",
            )
        snapshots = await self.repository.list_snapshots_by_proposal(proposal.id)
        pre_snapshot = next(
            (item for item in snapshots if item.snapshot_type == SnapshotType.pre_apply),
            None,
        )
        if pre_snapshot is None:
            raise NotFoundError(
                "AGENTOPS_ADAPTATION_SNAPSHOT_NOT_FOUND",
                "Pre-apply snapshot not found",
            )
        now = utcnow()
        if pre_snapshot.retention_expires_at < now:
            raise RollbackWindowExpiredError(proposal.id)
        restored_state = pre_snapshot.configuration.get("profile_fields", {})
        await self.registry_service.update_profile_fields(
            proposal.agent_fqn,
            proposal.workspace_id,
            restored_state,
        )
        current_state = await self.registry_service.get_profile_state(
            proposal.agent_fqn,
            proposal.workspace_id,
        )
        if current_state is None:
            raise ValidationError(
                "AGENTOPS_ADAPTATION_ORPHANED",
                "Agent state disappeared during rollback.",
            )
        current_hash = configuration_hash(snapshot_payload(current_state))
        if current_hash != pre_snapshot.configuration_hash:
            raise RollbackIntegrityError(proposal.id)
        proposal.status = AdaptationProposalStatus.rolled_back
        proposal.rolled_back_at = now
        proposal.rolled_back_by = actor
        proposal.rollback_reason = reason
        proposal.completion_note = reason
        updated = await self.repository.update_adaptation(proposal)
        await self._record_event(
            AgentOpsEventType.adaptation_rolled_back.value,
            updated,
            actor=actor,
            payload={
                "proposal_id": str(updated.id),
                "restored_snapshot_id": str(pre_snapshot.id),
                "restored_configuration_hash": current_hash,
            },
        )
        return AdaptationRollbackResponse(
            proposal=AdaptationProposalResponse.model_validate(updated),
            byte_identical_to_pre_apply=True,
        )

    async def _record_event(
        self,
        event_type: str,
        proposal: Any,
        *,
        actor: UUID,
        payload: dict[str, object],
    ) -> None:
        if self.governance_publisher is None:
            return
        await self.governance_publisher.record(
            event_type,
            proposal.agent_fqn,
            proposal.workspace_id,
            payload=payload,
            actor=actor,
            revision_id=proposal.revision_id,
        )


def snapshot_payload(state: dict[str, Any]) -> dict[str, object]:
    return {
        "profile_fields": {
            key: state.get(key)
            for key in (
                "display_name",
                "purpose",
                "approach",
                "role_types",
                "custom_role_description",
                "tags",
                "visibility_agents",
                "visibility_tools",
                "mcp_server_refs",
            )
        },
        "active_revision_id": str(state.get("revision_id")) if state.get("revision_id") else None,
    }


def configuration_hash(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
