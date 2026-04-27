from __future__ import annotations

from datetime import datetime
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.common.logging import get_logger
from platform.execution.exceptions import ExecutionNotFoundError
from platform.interactions.exceptions import InteractionNotFoundError
from platform.mock_llm.service import MockLLMService
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
    ContractTemplateListResponse,
    ContractTemplateResponse,
    PreviewResponse,
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
LOGGER = get_logger(__name__)


class ContractService:
    def __init__(
        self,
        repository: TrustRepository,
        publisher: object | None,
        mock_llm_service: MockLLMService | None = None,
    ) -> None:
        self.repository = repository
        self.events = publisher if publisher is not None else None
        self.mock_llm_service = mock_llm_service or MockLLMService()

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
        trend = (
            []
            if total == 0
            else [ComplianceTrendPoint.model_validate(item) for item in stats.get("trend", [])]
        )
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

    async def preview_contract(
        self,
        contract_id: UUID,
        sample_input: dict[str, object],
        *,
        use_mock: bool = True,
        cost_acknowledged: bool = False,
        workspace_id: UUID | None = None,
    ) -> PreviewResponse:
        contract = await self._require_contract(contract_id)
        self._ensure_workspace(contract, workspace_id)
        if not use_mock and not cost_acknowledged:
            raise ValidationError(
                "TRUST_REAL_LLM_PREVIEW_REQUIRES_ACK",
                "Real LLM preview requires explicit cost acknowledgement",
            )

        clauses = self._preview_clauses(contract)
        violated = self._preview_violations(contract, sample_input)
        satisfied = [clause for clause in clauses if clause not in violated]
        final_action = contract.enforcement_policy if violated else "continue"
        mock_response = None
        was_fallback = False
        if use_mock:
            mock = await self.mock_llm_service.preview(
                str(sample_input),
                {"contract_id": str(contract_id), "agent_id": contract.agent_id},
            )
            mock_response = mock.output_text
            was_fallback = mock.was_fallback
        else:
            LOGGER.info(
                "creator.contract.real_llm_preview_used",
                contract_id=str(contract_id),
                workspace_id=str(contract.workspace_id),
            )
        LOGGER.info(
            "creator.contract.preview_executed",
            contract_id=str(contract_id),
            workspace_id=str(contract.workspace_id),
            use_mock=use_mock,
            violations=len(violated),
        )
        return PreviewResponse(
            clauses_triggered=clauses,
            clauses_satisfied=satisfied,
            clauses_violated=violated,
            final_action=final_action,
            mock_response=mock_response,
            was_fallback=was_fallback,
        )

    async def list_templates(self) -> ContractTemplateListResponse:
        items = await self.repository.list_contract_templates()
        return ContractTemplateListResponse(
            items=[ContractTemplateResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def fork_template(
        self,
        template_id: UUID,
        new_name: str,
        workspace_id: UUID,
        requester_id: UUID,
    ) -> AgentContractResponse:
        template = await self.repository.get_contract_template(template_id)
        if template is None or not template.is_published:
            raise ContractNotFoundError(template_id)
        content = dict(template.template_content or {})
        contract = await self.repository.create_contract(
            AgentContract(
                workspace_id=workspace_id,
                agent_id=new_name,
                task_scope=str(content.get("task_scope") or template.name),
                expected_outputs=content.get("expected_outputs"),
                quality_thresholds=content.get("quality_thresholds"),
                time_constraint_seconds=content.get("time_constraint_seconds"),
                cost_limit_tokens=content.get("cost_limit_tokens"),
                escalation_conditions={
                    **dict(content.get("escalation_conditions") or {}),
                    "_forked_from_template_id": str(template.id),
                    "_forked_from_template_version": template.version_number,
                },
                success_criteria=content.get("success_criteria"),
                enforcement_policy=str(content.get("enforcement_policy") or "warn"),
                is_archived=False,
                created_by=requester_id,
                updated_by=requester_id,
            )
        )
        LOGGER.info(
            "creator.contract.forked_from_template",
            template_id=str(template_id),
            contract_id=str(contract.id),
            workspace_id=str(workspace_id),
            actor_id=str(requester_id),
        )
        return AgentContractResponse.model_validate(contract)

    async def attach_to_revision(
        self,
        contract_id: UUID,
        revision_id: UUID,
        requester_id: UUID,
        *,
        workspace_id: UUID | None = None,
    ) -> None:
        contract = await self._require_contract(contract_id)
        self._ensure_workspace(contract, workspace_id)
        if contract.is_archived:
            raise ValidationError(
                "TRUST_CONTRACT_ARCHIVED",
                "Archived contracts cannot be attached to revisions",
            )
        revision_row = await self.repository.get_agent_revision_with_profile(revision_id)
        if revision_row is None:
            raise ValidationError(
                "REGISTRY_REVISION_NOT_FOUND",
                "Agent revision not found",
                {"revision_id": str(revision_id)},
            )
        revision, profile = revision_row
        if workspace_id is not None and revision.workspace_id != workspace_id:
            raise AuthorizationError(
                "TRUST_CONTRACT_REVISION_WORKSPACE_MISMATCH",
                "Revision does not belong to the current workspace",
            )
        if contract.agent_id not in {profile.fqn, str(profile.id)}:
            raise ValidationError(
                "TRUST_CONTRACT_REVISION_AGENT_MISMATCH",
                "Contract agent_id does not match the target revision",
                {"contract_agent_id": contract.agent_id, "revision_agent_fqn": profile.fqn},
            )
        await self.repository.update_contract(
            contract_id,
            {
                "attached_revision_id": revision_id,
                "updated_by": self._to_uuid_or_none(requester_id),
            },
        )
        LOGGER.info(
            "creator.contract.attached_to_revision",
            contract_id=str(contract_id),
            revision_id=str(revision_id),
            actor_id=str(requester_id),
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
    def _preview_clauses(contract: AgentContract) -> list[str]:
        clauses = ["task_scope", "enforcement_policy"]
        if contract.expected_outputs:
            clauses.append("expected_outputs")
        if contract.quality_thresholds:
            clauses.append("quality_thresholds")
        if contract.time_constraint_seconds is not None:
            clauses.append("time_constraint_seconds")
        if contract.cost_limit_tokens is not None:
            clauses.append("cost_limit_tokens")
        if contract.escalation_conditions:
            clauses.append("escalation_conditions")
        if contract.success_criteria:
            clauses.append("success_criteria")
        return clauses

    @staticmethod
    def _preview_violations(
        contract: AgentContract,
        sample_input: dict[str, object],
    ) -> list[str]:
        violations: list[str] = []
        output = sample_input.get("output")
        if contract.expected_outputs and isinstance(output, dict):
            required = contract.expected_outputs.get("required")
            if isinstance(required, list):
                missing = [field for field in required if field not in output]
                if missing:
                    violations.append("expected_outputs")
        if contract.cost_limit_tokens is not None:
            observed_tokens = sample_input.get("tokens")
            if isinstance(observed_tokens, int) and observed_tokens > contract.cost_limit_tokens:
                violations.append("cost_limit_tokens")
        if sample_input.get("force_violation") is True and "success_criteria" not in violations:
            violations.append("success_criteria")
        text = str(sample_input).lower()
        if "secret" in text and contract.escalation_conditions:
            violations.append("escalation_conditions")
        return list(dict.fromkeys(violations))

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
