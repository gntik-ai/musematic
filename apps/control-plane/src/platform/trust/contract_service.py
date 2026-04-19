from __future__ import annotations

from datetime import datetime
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.execution.exceptions import ExecutionNotFoundError
from platform.interactions.exceptions import InteractionNotFoundError
from platform.trust.contract_schemas import (
    AgentContractCreate,
    AgentContractListResponse,
    AgentContractResponse,
    AgentContractUpdate,
    ComplianceRateQuery,
    ComplianceRateResponse,
    ComplianceTrendPoint,
    ContractBreachEventListResponse,
    ContractBreachEventResponse,
)
from platform.trust.events import (
    ContractBreachPayload,
    ContractEnforcementPayload,
    make_correlation,
    utcnow,
)
from platform.trust.exceptions import ContractConflictError, ContractNotFoundError
from platform.trust.models import AgentContract, ContractBreachEvent
from platform.trust.repository import TrustRepository
from uuid import UUID

ALLOWED_ENFORCEMENT_POLICIES = {"warn", "throttle", "escalate", "terminate"}


class ContractService:
    def __init__(self, repository: TrustRepository, publisher: object | None) -> None:
        self.repository = repository
        self.events = publisher if publisher is not None else None

    async def create_contract(
        self,
        data: AgentContractCreate,
        workspace_id: UUID,
        actor_id: UUID | str | None,
    ) -> AgentContractResponse:
        payload = data.model_dump()
        self._validate_contract_payload(payload)
        contract = await self.repository.create_contract(
            AgentContract(
                workspace_id=workspace_id,
                agent_id=payload["agent_id"],
                task_scope=payload["task_scope"],
                expected_outputs=payload.get("expected_outputs"),
                quality_thresholds=payload.get("quality_thresholds"),
                time_constraint_seconds=payload.get("time_constraint_seconds"),
                cost_limit_tokens=payload.get("cost_limit_tokens"),
                escalation_conditions=payload.get("escalation_conditions"),
                success_criteria=payload.get("success_criteria"),
                enforcement_policy=payload["enforcement_policy"],
                is_archived=False,
                created_by=self._to_uuid_or_none(actor_id),
                updated_by=self._to_uuid_or_none(actor_id),
            )
        )
        return AgentContractResponse.model_validate(contract)

    async def get_contract(
        self,
        contract_id: UUID,
        *,
        workspace_id: UUID | None = None,
    ) -> AgentContractResponse:
        contract = await self._require_contract(contract_id)
        self._ensure_workspace(contract, workspace_id)
        return AgentContractResponse.model_validate(contract)

    async def list_contracts(
        self,
        workspace_id: UUID,
        *,
        agent_id: str | None = None,
        include_archived: bool = False,
    ) -> AgentContractListResponse:
        items = await self.repository.list_contracts(workspace_id, agent_id, include_archived)
        return AgentContractListResponse(
            items=[AgentContractResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def update_contract(
        self,
        contract_id: UUID,
        data: AgentContractUpdate,
        actor_id: UUID | str | None,
        *,
        workspace_id: UUID | None = None,
    ) -> AgentContractResponse:
        contract = await self._require_contract(contract_id)
        self._ensure_workspace(contract, workspace_id)
        payload = data.model_dump(exclude_unset=True)
        effective = {
            "expected_outputs": payload.get("expected_outputs", contract.expected_outputs),
            "quality_thresholds": payload.get("quality_thresholds", contract.quality_thresholds),
            "time_constraint_seconds": payload.get(
                "time_constraint_seconds",
                contract.time_constraint_seconds,
            ),
            "cost_limit_tokens": payload.get("cost_limit_tokens", contract.cost_limit_tokens),
            "escalation_conditions": payload.get(
                "escalation_conditions",
                contract.escalation_conditions,
            ),
            "success_criteria": payload.get("success_criteria", contract.success_criteria),
            "enforcement_policy": payload.get(
                "enforcement_policy",
                contract.enforcement_policy,
            ),
        }
        self._validate_contract_payload(effective)
        payload["updated_by"] = self._to_uuid_or_none(actor_id)
        updated = await self.repository.update_contract(contract_id, payload)
        if updated is None:
            raise ContractNotFoundError(contract_id)
        return AgentContractResponse.model_validate(updated)

    async def archive_contract(
        self,
        contract_id: UUID,
        actor_id: UUID | str | None,
        *,
        workspace_id: UUID | None = None,
    ) -> None:
        contract = await self._require_contract(contract_id)
        self._ensure_workspace(contract, workspace_id)
        if await self.repository.has_inflight_execution_for_contract(contract_id):
            raise ContractConflictError(
                "TRUST_CONTRACT_IN_USE",
                "Contract cannot be archived while attached to in-flight executions",
                {"contract_id": str(contract_id)},
            )
        contract.updated_by = self._to_uuid_or_none(actor_id)
        await self.repository.archive_contract(contract_id)

    async def attach_to_interaction(
        self,
        interaction_id: UUID,
        contract_id: UUID,
        *,
        workspace_id: UUID | None = None,
    ) -> None:
        contract = await self._require_contract(contract_id)
        self._ensure_workspace(contract, workspace_id)
        if contract.is_archived:
            raise ValidationError(
                "TRUST_CONTRACT_ARCHIVED",
                "Archived contracts cannot be attached",
            )
        attached = await self.repository.attach_contract_to_interaction(
            interaction_id,
            contract_id,
            self._snapshot(contract),
        )
        if attached is None:
            raise InteractionNotFoundError(interaction_id)

    async def attach_to_execution(
        self,
        execution_id: UUID,
        contract_id: UUID,
        *,
        workspace_id: UUID | None = None,
    ) -> None:
        contract = await self._require_contract(contract_id)
        self._ensure_workspace(contract, workspace_id)
        if contract.is_archived:
            raise ValidationError(
                "TRUST_CONTRACT_ARCHIVED",
                "Archived contracts cannot be attached",
            )
        attached = await self.repository.attach_contract_to_execution(
            execution_id,
            contract_id,
            self._snapshot(contract),
        )
        if attached is None:
            raise ExecutionNotFoundError(execution_id)

    async def get_attached_execution_snapshot(self, execution_id: UUID) -> dict[str, object] | None:
        return await self.repository.get_execution_contract_snapshot(execution_id)

    async def get_attached_interaction_snapshot(
        self,
        interaction_id: UUID,
    ) -> dict[str, object] | None:
        return await self.repository.get_interaction_contract_snapshot(interaction_id)

    async def list_breach_events(
        self,
        contract_id: UUID,
        *,
        workspace_id: UUID | None = None,
        target_type: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> ContractBreachEventListResponse:
        contract = await self._require_contract(contract_id)
        self._ensure_workspace(contract, workspace_id)
        items, total = await self.repository.list_breach_events(
            contract_id,
            target_type=target_type,
            start=start,
            end=end,
            offset=offset,
            limit=limit,
        )
        return ContractBreachEventListResponse(
            items=[ContractBreachEventResponse.model_validate(item) for item in items],
            total=total,
        )

    async def record_breach(
        self,
        *,
        contract: AgentContract,
        target_type: str,
        target_id: UUID,
        breached_term: str,
        observed_value: dict[str, object],
        threshold_value: dict[str, object],
        enforcement_action: str,
        enforcement_outcome: str,
    ) -> ContractBreachEvent:
        existing, _ = await self.repository.list_breach_events(contract.id, target_type=target_type)
        for item in existing:
            if (
                item.target_id == target_id
                and item.breached_term == breached_term
                and item.enforcement_action == enforcement_action
            ):
                return item
        breach = await self.repository.create_breach_event(
            ContractBreachEvent(
                contract_id=contract.id,
                target_type=target_type,
                target_id=target_id,
                breached_term=breached_term,
                observed_value=dict(observed_value),
                threshold_value=dict(threshold_value),
                enforcement_action=enforcement_action,
                enforcement_outcome=enforcement_outcome,
                contract_snapshot=self._snapshot(contract),
            )
        )
        publisher = getattr(self.events, "publish_contract_breach", None)
        if callable(publisher):
            await publisher(
                ContractBreachPayload(
                    breach_event_id=breach.id,
                    contract_id=contract.id,
                    agent_id=contract.agent_id,
                    target_type=target_type,
                    target_id=target_id,
                    breached_term=breached_term,
                    enforcement_action=enforcement_action,
                    enforcement_outcome=enforcement_outcome,
                    occurred_at=utcnow(),
                ),
                make_correlation(),
            )
        return breach

    async def publish_enforcement(
        self,
        *,
        contract: AgentContract,
        breach_event_id: UUID | None,
        target_type: str,
        target_id: UUID,
        action: str,
        outcome: str,
    ) -> None:
        publisher = getattr(self.events, "publish_contract_enforcement", None)
        if callable(publisher):
            await publisher(
                ContractEnforcementPayload(
                    contract_id=contract.id,
                    breach_event_id=breach_event_id,
                    action=action,
                    outcome=outcome,
                    target_type=target_type,
                    target_id=target_id,
                    occurred_at=utcnow(),
                ),
                make_correlation(),
            )

    async def get_compliance_rates(
        self,
        query: ComplianceRateQuery,
        workspace_id: UUID,
    ) -> ComplianceRateResponse:
        del workspace_id
        stats = await self.repository.get_compliance_stats(
            query.scope,
            query.scope_id,
            query.start,
            query.end,
            query.bucket,
        )
        total = int(stats["total_contract_attached"])
        compliance_rate = None if total == 0 else float(stats["compliant"]) / float(total)
        trend = [] if total == 0 else [
            ComplianceTrendPoint.model_validate(item) for item in stats.get("trend", [])
        ]
        return ComplianceRateResponse(
            scope=query.scope,
            scope_id=query.scope_id,
            start=query.start,
            end=query.end,
            total_contract_attached=total,
            compliant=int(stats["compliant"]),
            warned=int(stats["warned"]),
            throttled=int(stats["throttled"]),
            escalated=int(stats["escalated"]),
            terminated=int(stats["terminated"]),
            compliance_rate=compliance_rate,
            breach_by_term={
                str(key): int(value) for key, value in stats.get("breach_by_term", {}).items()
            },
            trend=trend,
        )

    async def _require_contract(self, contract_id: UUID) -> AgentContract:
        contract = await self.repository.get_contract(contract_id)
        if contract is None:
            raise ContractNotFoundError(contract_id)
        return contract

    @staticmethod
    def _ensure_workspace(contract: AgentContract, workspace_id: UUID | None) -> None:
        if workspace_id is not None and contract.workspace_id != workspace_id:
            raise AuthorizationError(
                "TRUST_CONTRACT_WORKSPACE_MISMATCH",
                "Contract does not belong to the current workspace",
            )

    def _snapshot(self, contract: AgentContract) -> dict[str, object]:
        return AgentContractResponse.model_validate(contract).model_dump(mode="json")

    @staticmethod
    def _to_uuid_or_none(value: UUID | str | None) -> UUID | None:
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except ValueError:
            return None

    @staticmethod
    def _validate_contract_payload(payload: dict[str, object]) -> None:
        enforcement_policy = payload.get("enforcement_policy")
        if enforcement_policy not in ALLOWED_ENFORCEMENT_POLICIES:
            raise ValidationError(
                "TRUST_INVALID_ENFORCEMENT_POLICY",
                "Invalid enforcement policy",
                {"enforcement_policy": enforcement_policy},
            )
        for field in ("time_constraint_seconds", "cost_limit_tokens"):
            value = payload.get(field)
            if isinstance(value, int):
                numeric_value = value
            elif value is not None:
                numeric_value = int(str(value))
            else:
                numeric_value = None
            if numeric_value is not None and numeric_value < 1:
                raise ValidationError(
                    "TRUST_INVALID_CONTRACT_LIMIT",
                    f"{field} must be greater than or equal to 1",
                    {"field": field, "value": value},
                )
        cost_limit = payload.get("cost_limit_tokens")
        expected_outputs = payload.get("expected_outputs")
        if cost_limit == 0 and expected_outputs:
            raise ValidationError(
                "TRUST_CONFLICTING_CONTRACT_TERMS",
                "cost_limit_tokens=0 conflicts with expected_outputs",
            )
