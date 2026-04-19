from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from platform.agentops.events import AgentOpsEventType, GovernanceEventPublisher
from platform.agentops.exceptions import StaleProposalError
from platform.agentops.models import (
    AdaptationProposal,
    AdaptationProposalStatus,
    AdaptationSnapshot,
    SnapshotType,
)
from platform.agentops.repository import AgentOpsRepository
from platform.agentops.schemas import AdaptationApplyResponse, AdaptationProposalResponse
from platform.common.exceptions import NotFoundError, ValidationError
from typing import Any, cast
from uuid import UUID, uuid4

_PROFILE_FIELDS: tuple[str, ...] = (
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

_TARGET_FIELDS: dict[str, tuple[str, ...]] = {
    "context_profile": ("mcp_server_refs", "tags"),
    "model_params": ("approach",),
    "approach_text": ("approach",),
    "tool_selection": ("visibility_tools", "mcp_server_refs"),
    "self_correction_strategy": ("approach",),
}


def utcnow() -> datetime:
    return datetime.now(UTC)


class AdaptationApplyService:
    def __init__(
        self,
        *,
        repository: AgentOpsRepository,
        registry_service: Any,
        governance_publisher: GovernanceEventPublisher | None,
        rollback_retention_days: int,
        observation_window_hours: int,
    ) -> None:
        self.repository = repository
        self.registry_service = registry_service
        self.governance_publisher = governance_publisher
        self.rollback_retention_days = rollback_retention_days
        self.observation_window_hours = observation_window_hours

    async def apply(
        self,
        proposal_id: UUID,
        *,
        actor: UUID,
        reason: str | None = None,
    ) -> AdaptationApplyResponse:
        proposal = await self.repository.get_adaptation(proposal_id)
        if proposal is None:
            raise NotFoundError("AGENTOPS_ADAPTATION_NOT_FOUND", "Adaptation proposal not found")
        if proposal.status != AdaptationProposalStatus.approved.value:
            raise ValidationError(
                "AGENTOPS_ADAPTATION_NOT_APPROVED",
                "Only approved proposals can be applied.",
            )
        current_state = await self.registry_service.get_profile_state(
            proposal.agent_fqn,
            proposal.workspace_id,
        )
        if current_state is None:
            proposal.status = AdaptationProposalStatus.orphaned
            await self.repository.update_adaptation(proposal)
            raise ValidationError(
                "AGENTOPS_ADAPTATION_ORPHANED",
                "Adaptation proposal no longer points to an active agent.",
            )
        current_snapshot = state_to_snapshot(current_state)
        profile_fields = cast(dict[str, Any], current_snapshot["profile_fields"])
        if is_stale(profile_fields, proposal.proposal_details):
            proposal.status = AdaptationProposalStatus.stale
            proposal.completed_at = utcnow()
            proposal.completion_note = "Proposal became stale before apply."
            await self.repository.update_adaptation(proposal)
            await self._record_event(
                AgentOpsEventType.adaptation_stale.value,
                proposal,
                actor=actor,
                payload={"proposal_id": str(proposal.id)},
            )
            raise StaleProposalError(proposal.id)

        now = utcnow()
        pre_snapshot = await self.repository.create_snapshot(
            AdaptationSnapshot(
                id=uuid4(),
                proposal_id=proposal.id,
                snapshot_type=SnapshotType.pre_apply,
                configuration_hash=configuration_hash(current_snapshot),
                configuration=current_snapshot,
                revision_id=coerce_uuid(current_state.get("revision_id")),
                retention_expires_at=now + timedelta(days=self.rollback_retention_days),
            )
        )
        updated_fields = apply_adjustments(profile_fields, proposal.proposal_details)
        try:
            applied_state = await self.registry_service.update_profile_fields(
                proposal.agent_fqn,
                proposal.workspace_id,
                updated_fields,
            )
        except Exception:
            await self.registry_service.update_profile_fields(
                proposal.agent_fqn,
                proposal.workspace_id,
                current_snapshot["profile_fields"],
            )
            proposal.proposal_details = {
                **dict(proposal.proposal_details or {}),
                "recovery_path": "auto_rollback",
            }
            await self.repository.update_adaptation(proposal)
            raise
        if applied_state is None:
            raise ValidationError(
                "AGENTOPS_ADAPTATION_APPLY_FAILED",
                "Agent state could not be updated.",
            )
        post_snapshot_state = state_to_snapshot(applied_state)
        post_snapshot = await self.repository.create_snapshot(
            AdaptationSnapshot(
                id=uuid4(),
                proposal_id=proposal.id,
                snapshot_type=SnapshotType.post_apply,
                configuration_hash=configuration_hash(post_snapshot_state),
                configuration=post_snapshot_state,
                revision_id=coerce_uuid(applied_state.get("revision_id")),
                retention_expires_at=pre_snapshot.retention_expires_at,
            )
        )
        proposal.status = AdaptationProposalStatus.applied
        proposal.applied_at = now
        proposal.applied_by = actor
        proposal.pre_apply_snapshot_key = str(pre_snapshot.id)
        proposal.completion_note = reason or "Adaptation applied successfully."
        proposal.proposal_details = {
            **dict(proposal.proposal_details or {}),
            "pre_apply_snapshot_id": str(pre_snapshot.id),
            "post_apply_snapshot_id": str(post_snapshot.id),
            "post_apply_configuration_hash": post_snapshot.configuration_hash,
        }
        updated = await self.repository.update_adaptation(proposal)
        await self._record_event(
            AgentOpsEventType.adaptation_applied.value,
            updated,
            actor=actor,
            payload={
                "proposal_id": str(updated.id),
                "pre_apply_snapshot_id": str(pre_snapshot.id),
                "post_apply_snapshot_id": str(post_snapshot.id),
                "pre_apply_configuration_hash": pre_snapshot.configuration_hash,
                "post_apply_configuration_hash": post_snapshot.configuration_hash,
                "outcome_measurement_scheduled_at": (
                    updated.applied_at + timedelta(hours=self.observation_window_hours)
                ).isoformat()
                if updated.applied_at is not None
                else None,
            },
        )
        return AdaptationApplyResponse(
            proposal=AdaptationProposalResponse.model_validate(updated),
            pre_apply_configuration_hash=pre_snapshot.configuration_hash,
        )

    async def _record_event(
        self,
        event_type: str,
        proposal: AdaptationProposal,
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


def coerce_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def configuration_hash(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def state_to_snapshot(state: dict[str, Any]) -> dict[str, object]:
    profile_fields = {field: deepcopy(state.get(field)) for field in _PROFILE_FIELDS}
    return {
        "profile_fields": profile_fields,
        "active_revision_id": str(state.get("revision_id")) if state.get("revision_id") else None,
    }


def is_stale(profile_fields: dict[str, Any], proposal_details: dict[str, Any]) -> bool:
    adjustments = (
        proposal_details.get("adjustments", []) if isinstance(proposal_details, dict) else []
    )
    for item in adjustments:
        if not isinstance(item, dict):
            continue
        target = str(item.get("target") or "")
        fields = _TARGET_FIELDS.get(target)
        if not fields:
            continue
        if all(is_missing(profile_fields.get(field)) for field in fields):
            return True
    return False


def is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def apply_adjustments(
    profile_fields: dict[str, Any],
    proposal_details: dict[str, Any],
) -> dict[str, object]:
    updated = deepcopy(profile_fields)
    adjustments = (
        proposal_details.get("adjustments", []) if isinstance(proposal_details, dict) else []
    )
    for item in adjustments:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or "")
        if action == "refresh_context_profile":
            tags = list(updated.get("tags") or [])
            if "context-refresh" not in tags:
                tags.append("context-refresh")
            updated["tags"] = tags
        elif action == "optimize_model_params":
            updated["approach"] = append_note(
                updated.get("approach"),
                "Cost profile tuned by agent adaptation.",
            )
        elif action == "revise_approach_text":
            updated["approach"] = append_note(
                updated.get("approach"),
                "Recovery guidance refreshed from recurring failures.",
            )
        elif action == "rebalance_tool_selection":
            tools = list(updated.get("visibility_tools") or [])
            if "balanced-tool" not in tools:
                tools.append("balanced-tool")
            updated["visibility_tools"] = tools
        elif action == "stabilize_convergence_strategy":
            updated["approach"] = append_note(
                updated.get("approach"),
                "Self-correction convergence guidance stabilized.",
            )
    return updated


def append_note(existing: object, note: str) -> str:
    base = str(existing).strip() if existing is not None else ""
    if not base:
        return note
    if note in base:
        return base
    return f"{base}\n\n{note}"
