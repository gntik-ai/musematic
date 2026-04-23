from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.execution.models import Execution, ExecutionStatus
from platform.interactions.models import Interaction
from platform.trust.exceptions import ContractConflictError
from platform.trust.models import (
    AgentContract,
    CertificationStatus,
    Certifier,
    ContractBreachEvent,
    GuardrailLayer,
    ReassessmentRecord,
    RecertificationTriggerStatus,
    RecertificationTriggerType,
    TrustATEConfiguration,
    TrustBlockedActionRecord,
    TrustCertification,
    TrustCertificationEvidenceRef,
    TrustCircuitBreakerConfig,
    TrustGuardrailPipelineConfig,
    TrustOJEPipelineConfig,
    TrustProofLink,
    TrustRecertificationRequest,
    TrustRecertificationTrigger,
    TrustSafetyPreScreenerRuleSet,
    TrustSignal,
    TrustTier,
    TrustTierName,
)
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class TrustRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_certification(self, certification: TrustCertification) -> TrustCertification:
        self.session.add(certification)
        await self.session.flush()
        return certification

    async def get_certification(self, certification_id: UUID) -> TrustCertification | None:
        result = await self.session.execute(
            select(TrustCertification)
            .options(selectinload(TrustCertification.evidence_refs))
            .where(TrustCertification.id == certification_id)
        )
        return result.scalar_one_or_none()

    async def list_certifications_for_agent(self, agent_id: str) -> list[TrustCertification]:
        result = await self.session.execute(
            select(TrustCertification)
            .options(selectinload(TrustCertification.evidence_refs))
            .where(TrustCertification.agent_id == agent_id)
            .order_by(TrustCertification.created_at.desc(), TrustCertification.id.desc())
        )
        return list(result.scalars().all())

    async def list_active_certifications_for_agent(self, agent_id: str) -> list[TrustCertification]:
        result = await self.session.execute(
            select(TrustCertification).where(
                TrustCertification.agent_id == agent_id,
                TrustCertification.status == CertificationStatus.active,
            )
        )
        return list(result.scalars().all())

    async def list_stale_certifications(self, now: datetime) -> list[TrustCertification]:
        result = await self.session.execute(
            select(TrustCertification).where(
                TrustCertification.status.in_(
                    (CertificationStatus.active, CertificationStatus.expiring)
                ),
                TrustCertification.expires_at.is_not(None),
                TrustCertification.expires_at < now,
            )
        )
        return list(result.scalars().all())

    async def create_certifier(self, certifier: Certifier) -> Certifier:
        self.session.add(certifier)
        await self.session.flush()
        return certifier

    async def get_certifier(self, certifier_id: UUID) -> Certifier | None:
        result = await self.session.execute(select(Certifier).where(Certifier.id == certifier_id))
        return result.scalar_one_or_none()

    async def list_certifiers(self, include_inactive: bool = False) -> list[Certifier]:
        query = select(Certifier).order_by(Certifier.name.asc(), Certifier.id.asc())
        if not include_inactive:
            query = query.where(Certifier.is_active.is_(True))
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def deactivate_certifier(self, certifier_id: UUID) -> Certifier | None:
        certifier = await self.get_certifier(certifier_id)
        if certifier is None:
            return None
        certifier.is_active = False
        await self.session.flush()
        return certifier

    async def create_contract(self, contract: AgentContract) -> AgentContract:
        self.session.add(contract)
        await self.session.flush()
        return contract

    async def get_contract(self, contract_id: UUID) -> AgentContract | None:
        result = await self.session.execute(
            select(AgentContract).where(AgentContract.id == contract_id)
        )
        return result.scalar_one_or_none()

    async def list_contracts(
        self,
        workspace_id: UUID,
        agent_id: str | None = None,
        include_archived: bool = False,
    ) -> list[AgentContract]:
        filters = [AgentContract.workspace_id == workspace_id]
        if agent_id is not None:
            filters.append(AgentContract.agent_id == agent_id)
        if not include_archived:
            filters.append(AgentContract.is_archived.is_(False))
        result = await self.session.execute(
            select(AgentContract)
            .where(*filters)
            .order_by(AgentContract.created_at.desc(), AgentContract.id.desc())
        )
        return list(result.scalars().all())

    async def update_contract(
        self,
        contract_id: UUID,
        data: dict[str, Any],
    ) -> AgentContract | None:
        contract = await self.get_contract(contract_id)
        if contract is None:
            return None
        for field, value in data.items():
            setattr(contract, field, value)
        await self.session.flush()
        return contract

    async def archive_contract(self, contract_id: UUID) -> AgentContract | None:
        contract = await self.get_contract(contract_id)
        if contract is None:
            return None
        contract.is_archived = True
        await self.session.flush()
        return contract

    async def has_inflight_execution_for_contract(self, contract_id: UUID) -> bool:
        total = await self.session.scalar(
            select(func.count())
            .select_from(Execution)
            .where(
                Execution.contract_id == contract_id,
                Execution.status.in_(
                    (
                        ExecutionStatus.queued,
                        ExecutionStatus.running,
                        ExecutionStatus.waiting_for_approval,
                        ExecutionStatus.compensating,
                    )
                ),
            )
        )
        return bool(total)

    async def get_interaction_contract_snapshot(
        self,
        interaction_id: UUID,
    ) -> dict[str, Any] | None:
        result = await self.session.execute(
            select(Interaction.contract_snapshot).where(Interaction.id == interaction_id)
        )
        return result.scalar_one_or_none()

    async def get_execution_contract_snapshot(self, execution_id: UUID) -> dict[str, Any] | None:
        result = await self.session.execute(
            select(Execution.contract_snapshot).where(Execution.id == execution_id)
        )
        return result.scalar_one_or_none()

    async def attach_contract_to_interaction(
        self,
        interaction_id: UUID,
        contract_id: UUID,
        snapshot: dict[str, Any],
    ) -> Interaction | None:
        interaction = await self.session.get(Interaction, interaction_id)
        if interaction is None:
            return None
        if interaction.contract_id is not None and interaction.contract_id != contract_id:
            raise ContractConflictError(
                "TRUST_CONTRACT_ALREADY_ATTACHED",
                "Interaction already has a different contract attached",
                {
                    "interaction_id": str(interaction_id),
                    "existing_contract_id": str(interaction.contract_id),
                    "requested_contract_id": str(contract_id),
                },
            )
        interaction.contract_id = contract_id
        interaction.contract_snapshot = dict(snapshot)
        await self.session.flush()
        return interaction

    async def attach_contract_to_execution(
        self,
        execution_id: UUID,
        contract_id: UUID,
        snapshot: dict[str, Any],
    ) -> Execution | None:
        execution = await self.session.get(Execution, execution_id)
        if execution is None:
            return None
        if execution.contract_id is not None and execution.contract_id != contract_id:
            raise ContractConflictError(
                "TRUST_CONTRACT_ALREADY_ATTACHED",
                "Execution already has a different contract attached",
                {
                    "execution_id": str(execution_id),
                    "existing_contract_id": str(execution.contract_id),
                    "requested_contract_id": str(contract_id),
                },
            )
        execution.contract_id = contract_id
        execution.contract_snapshot = dict(snapshot)
        await self.session.flush()
        return execution

    async def create_breach_event(self, breach_event: ContractBreachEvent) -> ContractBreachEvent:
        self.session.add(breach_event)
        await self.session.flush()
        return breach_event

    async def list_breach_events(
        self,
        contract_id: UUID,
        *,
        target_type: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ContractBreachEvent], int]:
        filters = [ContractBreachEvent.contract_id == contract_id]
        if target_type is not None:
            filters.append(ContractBreachEvent.target_type == target_type)
        if start is not None:
            filters.append(ContractBreachEvent.created_at >= start)
        if end is not None:
            filters.append(ContractBreachEvent.created_at <= end)
        total = await self.session.scalar(
            select(func.count()).select_from(ContractBreachEvent).where(*filters)
        )
        result = await self.session.execute(
            select(ContractBreachEvent)
            .where(*filters)
            .order_by(ContractBreachEvent.created_at.desc(), ContractBreachEvent.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def create_reassessment(
        self,
        certification_id: UUID,
        data: ReassessmentRecord,
    ) -> ReassessmentRecord:
        data.certification_id = certification_id
        self.session.add(data)
        await self.session.flush()
        return data

    async def list_reassessments(self, certification_id: UUID) -> list[ReassessmentRecord]:
        result = await self.session.execute(
            select(ReassessmentRecord)
            .where(ReassessmentRecord.certification_id == certification_id)
            .order_by(ReassessmentRecord.created_at.desc(), ReassessmentRecord.id.desc())
        )
        return list(result.scalars().all())

    async def create_recertification_request(
        self,
        request: TrustRecertificationRequest,
    ) -> TrustRecertificationRequest:
        self.session.add(request)
        await self.session.flush()
        return request

    async def get_recertification_request(
        self,
        request_id: UUID,
    ) -> TrustRecertificationRequest | None:
        result = await self.session.execute(
            select(TrustRecertificationRequest).where(TrustRecertificationRequest.id == request_id)
        )
        return result.scalar_one_or_none()

    async def list_recertification_requests(
        self,
        *,
        certification_id: UUID | None = None,
        status: str | None = None,
    ) -> list[TrustRecertificationRequest]:
        filters = []
        if certification_id is not None:
            filters.append(TrustRecertificationRequest.certification_id == certification_id)
        if status is not None:
            filters.append(TrustRecertificationRequest.resolution_status == status)
        result = await self.session.execute(
            select(TrustRecertificationRequest)
            .where(*filters)
            .order_by(
                TrustRecertificationRequest.created_at.desc(),
                TrustRecertificationRequest.id.desc(),
            )
        )
        return list(result.scalars().all())

    async def get_pending_requests_past_deadline(
        self,
        now: datetime,
    ) -> list[TrustRecertificationRequest]:
        result = await self.session.execute(
            select(TrustRecertificationRequest).where(
                TrustRecertificationRequest.resolution_status == "pending",
                TrustRecertificationRequest.deadline.is_not(None),
                TrustRecertificationRequest.deadline < now,
            )
        )
        return list(result.scalars().all())

    async def resolve_recertification_request(
        self,
        request_id: UUID,
        status: str,
        justification: str | None = None,
    ) -> TrustRecertificationRequest | None:
        request = await self.get_recertification_request(request_id)
        if request is None:
            return None
        request.resolution_status = status
        request.dismissal_justification = justification
        await self.session.flush()
        return request

    async def get_active_or_expiring_certifications_for_agent(
        self,
        agent_id: str,
    ) -> list[TrustCertification]:
        result = await self.session.execute(
            select(TrustCertification).where(
                TrustCertification.agent_id == agent_id,
                TrustCertification.status.in_(
                    (CertificationStatus.active, CertificationStatus.expiring)
                ),
            )
        )
        return list(result.scalars().all())

    async def get_compliance_stats(
        self,
        scope: str,
        scope_id: str,
        start: datetime,
        end: datetime,
        bucket: str,
    ) -> dict[str, Any]:
        def _bucket_value(dt: datetime) -> str:
            if bucket == "hourly":
                return dt.replace(minute=0, second=0, microsecond=0).isoformat()
            return dt.date().isoformat()

        execution_query = (
            select(Execution.id, Execution.created_at, Execution.contract_id)
            .where(
                Execution.contract_id.is_not(None),
                Execution.created_at >= start,
                Execution.created_at < end,
            )
            .join(AgentContract, AgentContract.id == Execution.contract_id)
        )
        interaction_query = select(Interaction.id, Interaction.created_at, Interaction.contract_id)
        interaction_query = interaction_query.where(
            Interaction.contract_id.is_not(None),
            Interaction.created_at >= start,
            Interaction.created_at < end,
        ).join(AgentContract, AgentContract.id == Interaction.contract_id)
        if scope == "workspace":
            workspace_id = UUID(scope_id)
            execution_query = execution_query.where(Execution.workspace_id == workspace_id)
            interaction_query = interaction_query.where(Interaction.workspace_id == workspace_id)
        elif scope == "agent":
            execution_query = execution_query.where(AgentContract.agent_id == scope_id)
            interaction_query = interaction_query.where(AgentContract.agent_id == scope_id)
        interaction_rows: list[Any] = []
        if scope == "fleet":
            fleet_id = UUID(scope_id)
            execution_query = execution_query.where(Execution.correlation_fleet_id == fleet_id)

        executions = list((await self.session.execute(execution_query)).all())
        if scope != "fleet":
            interaction_rows = list((await self.session.execute(interaction_query)).all())

        attachments: list[tuple[str, UUID, datetime, UUID | None]] = [
            ("execution", item.id, item.created_at, item.contract_id) for item in executions
        ] + [
            ("interaction", item.id, item.created_at, item.contract_id)
            for item in interaction_rows
        ]

        contract_ids = {
            contract_id
            for _, _, _, contract_id in attachments
            if contract_id is not None
        }
        breaches: list[ContractBreachEvent] = []
        if contract_ids:
            breaches = list(
                (
                    await self.session.execute(
                        select(ContractBreachEvent).where(
                            ContractBreachEvent.created_at >= start,
                            ContractBreachEvent.created_at < end,
                            ContractBreachEvent.contract_id.in_(contract_ids),
                        )
                    )
                ).scalars().all()
            )
        attachment_keys = {(target_type, target_id) for target_type, target_id, _, _ in attachments}
        filtered_breaches = [
            breach
            for breach in breaches
            if (breach.target_type, breach.target_id) in attachment_keys
        ]
        breached_targets = {
            (breach.target_type, breach.target_id)
            for breach in filtered_breaches
        }

        warned = sum(
            1 for breach in filtered_breaches if breach.enforcement_action == "warn"
        )
        throttled = sum(
            1 for breach in filtered_breaches if breach.enforcement_action == "throttle"
        )
        escalated = sum(
            1 for breach in filtered_breaches if breach.enforcement_action == "escalate"
        )
        terminated = sum(
            1 for breach in filtered_breaches if breach.enforcement_action == "terminate"
        )

        breach_by_term: dict[str, int] = {}
        for breach in filtered_breaches:
            breach_by_term[breach.breached_term] = breach_by_term.get(breach.breached_term, 0) + 1

        trend_map: dict[str, dict[str, int]] = {}
        for target_type, target_id, created_at, _ in attachments:
            bucket_value = _bucket_value(created_at)
            current = trend_map.setdefault(bucket_value, {"total": 0, "compliant": 0})
            current["total"] += 1
            if (target_type, target_id) not in breached_targets:
                current["compliant"] += 1
        total_contract_attached = len(attachments)
        compliant = total_contract_attached - len(breached_targets)

        return {
            "total_contract_attached": total_contract_attached,
            "compliant": compliant,
            "warned": warned,
            "throttled": throttled,
            "escalated": escalated,
            "terminated": terminated,
            "breach_by_term": breach_by_term,
            "trend": [
                {
                    "bucket": bucket_value,
                    "compliant": values["compliant"],
                    "total": values["total"],
                }
                for bucket_value, values in sorted(trend_map.items())
            ],
        }

    async def create_evidence_ref(
        self,
        evidence_ref: TrustCertificationEvidenceRef,
    ) -> TrustCertificationEvidenceRef:
        self.session.add(evidence_ref)
        await self.session.flush()
        return evidence_ref

    async def get_tier(self, agent_id: str) -> TrustTier | None:
        result = await self.session.execute(select(TrustTier).where(TrustTier.agent_id == agent_id))
        return result.scalar_one_or_none()

    async def upsert_trust_tier(
        self,
        *,
        agent_id: str,
        agent_fqn: str,
        tier: TrustTierName,
        trust_score: Decimal,
        certification_component: Decimal,
        guardrail_component: Decimal,
        behavioral_component: Decimal,
        last_computed_at: datetime,
    ) -> TrustTier:
        existing = await self.get_tier(agent_id)
        if existing is None:
            existing = TrustTier(
                agent_id=agent_id,
                agent_fqn=agent_fqn,
                tier=tier,
                trust_score=trust_score,
                certification_component=certification_component,
                guardrail_component=guardrail_component,
                behavioral_component=behavioral_component,
                last_computed_at=last_computed_at,
            )
            self.session.add(existing)
        else:
            existing.agent_fqn = agent_fqn
            existing.tier = tier
            existing.trust_score = trust_score
            existing.certification_component = certification_component
            existing.guardrail_component = guardrail_component
            existing.behavioral_component = behavioral_component
            existing.last_computed_at = last_computed_at
        await self.session.flush()
        return existing

    async def create_signal(self, signal: TrustSignal) -> TrustSignal:
        self.session.add(signal)
        await self.session.flush()
        return signal

    async def create_proof_link(self, proof_link: TrustProofLink) -> TrustProofLink:
        self.session.add(proof_link)
        await self.session.flush()
        return proof_link

    async def list_trust_signals_for_agent(
        self,
        agent_id: str,
        *,
        since: datetime | None = None,
        signal_type: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[TrustSignal], int]:
        filters = [TrustSignal.agent_id == agent_id]
        if since is not None:
            filters.append(TrustSignal.created_at >= since)
        if signal_type is not None:
            filters.append(TrustSignal.signal_type == signal_type)
        total = await self.session.scalar(
            select(func.count()).select_from(TrustSignal).where(*filters)
        )
        result = await self.session.execute(
            select(TrustSignal)
            .options(selectinload(TrustSignal.proof_links))
            .where(*filters)
            .order_by(TrustSignal.created_at.desc(), TrustSignal.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def create_trigger(
        self,
        trigger: TrustRecertificationTrigger,
    ) -> TrustRecertificationTrigger:
        self.session.add(trigger)
        await self.session.flush()
        return trigger

    async def get_trigger(self, trigger_id: UUID) -> TrustRecertificationTrigger | None:
        result = await self.session.execute(
            select(TrustRecertificationTrigger).where(TrustRecertificationTrigger.id == trigger_id)
        )
        return result.scalar_one_or_none()

    async def get_pending_trigger(
        self,
        *,
        agent_id: str,
        agent_revision_id: str,
        trigger_type: RecertificationTriggerType,
    ) -> TrustRecertificationTrigger | None:
        result = await self.session.execute(
            select(TrustRecertificationTrigger).where(
                TrustRecertificationTrigger.agent_id == agent_id,
                TrustRecertificationTrigger.agent_revision_id == agent_revision_id,
                TrustRecertificationTrigger.trigger_type == trigger_type,
                TrustRecertificationTrigger.status == RecertificationTriggerStatus.pending,
            )
        )
        return result.scalar_one_or_none()

    async def list_triggers(
        self,
        *,
        agent_id: str | None = None,
        status: RecertificationTriggerStatus | None = None,
    ) -> list[TrustRecertificationTrigger]:
        filters = []
        if agent_id is not None:
            filters.append(TrustRecertificationTrigger.agent_id == agent_id)
        if status is not None:
            filters.append(TrustRecertificationTrigger.status == status)
        result = await self.session.execute(
            select(TrustRecertificationTrigger)
            .where(*filters)
            .order_by(TrustRecertificationTrigger.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_pending_triggers(self) -> list[TrustRecertificationTrigger]:
        return await self.list_triggers(status=RecertificationTriggerStatus.pending)

    async def create_blocked_action_record(
        self,
        record: TrustBlockedActionRecord,
    ) -> TrustBlockedActionRecord:
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_blocked_action(self, record_id: UUID) -> TrustBlockedActionRecord | None:
        result = await self.session.execute(
            select(TrustBlockedActionRecord).where(TrustBlockedActionRecord.id == record_id)
        )
        return result.scalar_one_or_none()

    async def list_blocked_actions_paginated(
        self,
        *,
        agent_id: str | None = None,
        layer: GuardrailLayer | None = None,
        workspace_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[TrustBlockedActionRecord], int]:
        filters = []
        if agent_id is not None:
            filters.append(TrustBlockedActionRecord.agent_id == agent_id)
        if layer is not None:
            filters.append(TrustBlockedActionRecord.layer == layer)
        if workspace_id is not None:
            filters.append(TrustBlockedActionRecord.workspace_id == workspace_id)
        if since is not None:
            filters.append(TrustBlockedActionRecord.created_at >= since)
        if until is not None:
            filters.append(TrustBlockedActionRecord.created_at <= until)
        total = await self.session.scalar(
            select(func.count()).select_from(TrustBlockedActionRecord).where(*filters)
        )
        result = await self.session.execute(
            select(TrustBlockedActionRecord)
            .where(*filters)
            .order_by(
                TrustBlockedActionRecord.created_at.desc(), TrustBlockedActionRecord.id.desc()
            )
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def create_ate_config(self, config: TrustATEConfiguration) -> TrustATEConfiguration:
        self.session.add(config)
        await self.session.flush()
        return config

    async def get_ate_config(self, config_id: UUID) -> TrustATEConfiguration | None:
        result = await self.session.execute(
            select(TrustATEConfiguration).where(TrustATEConfiguration.id == config_id)
        )
        return result.scalar_one_or_none()

    async def list_ate_configs_for_workspace(
        self, workspace_id: str
    ) -> list[TrustATEConfiguration]:
        result = await self.session.execute(
            select(TrustATEConfiguration)
            .where(TrustATEConfiguration.workspace_id == workspace_id)
            .order_by(
                TrustATEConfiguration.name.asc(),
                TrustATEConfiguration.version.desc(),
                TrustATEConfiguration.created_at.desc(),
            )
        )
        return list(result.scalars().all())

    async def list_ate_config_versions(
        self,
        workspace_id: str,
        name: str,
    ) -> list[TrustATEConfiguration]:
        result = await self.session.execute(
            select(TrustATEConfiguration)
            .where(
                TrustATEConfiguration.workspace_id == workspace_id,
                TrustATEConfiguration.name == name,
            )
            .order_by(TrustATEConfiguration.version.desc())
        )
        return list(result.scalars().all())

    async def get_latest_ate_config_version(self, workspace_id: str, name: str) -> int:
        result = await self.session.scalar(
            select(func.max(TrustATEConfiguration.version)).where(
                TrustATEConfiguration.workspace_id == workspace_id,
                TrustATEConfiguration.name == name,
            )
        )
        return int(result or 0)

    async def deactivate_ate_configs(self, workspace_id: str, name: str) -> None:
        items = await self.list_ate_config_versions(workspace_id, name)
        for item in items:
            item.is_active = False
        await self.session.flush()

    async def create_guardrail_config(
        self,
        config: TrustGuardrailPipelineConfig,
    ) -> TrustGuardrailPipelineConfig:
        self.session.add(config)
        await self.session.flush()
        return config

    async def list_guardrail_configs(
        self,
        workspace_id: str,
    ) -> list[TrustGuardrailPipelineConfig]:
        result = await self.session.execute(
            select(TrustGuardrailPipelineConfig)
            .where(TrustGuardrailPipelineConfig.workspace_id == workspace_id)
            .order_by(TrustGuardrailPipelineConfig.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_guardrail_config(
        self,
        workspace_id: str,
        fleet_id: str | None = None,
    ) -> TrustGuardrailPipelineConfig | None:
        filters = [TrustGuardrailPipelineConfig.workspace_id == workspace_id]
        if fleet_id is not None:
            result = await self.session.execute(
                select(TrustGuardrailPipelineConfig).where(
                    *filters,
                    TrustGuardrailPipelineConfig.fleet_id == fleet_id,
                    TrustGuardrailPipelineConfig.is_active.is_(True),
                )
            )
            item = result.scalar_one_or_none()
            if item is not None:
                return item
        result = await self.session.execute(
            select(TrustGuardrailPipelineConfig).where(
                *filters,
                TrustGuardrailPipelineConfig.fleet_id.is_(None),
                TrustGuardrailPipelineConfig.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def upsert_guardrail_config(
        self,
        *,
        workspace_id: str,
        fleet_id: str | None,
        config: dict[str, Any],
        is_active: bool,
    ) -> TrustGuardrailPipelineConfig:
        existing = await self.get_guardrail_config(workspace_id, fleet_id)
        if existing is not None and (fleet_id is not None or existing.fleet_id is None):
            existing.config = config
            existing.is_active = is_active
            await self.session.flush()
            return existing
        created = TrustGuardrailPipelineConfig(
            workspace_id=workspace_id,
            fleet_id=fleet_id,
            config=config,
            is_active=is_active,
        )
        self.session.add(created)
        await self.session.flush()
        return created

    async def create_oje_config(self, config: TrustOJEPipelineConfig) -> TrustOJEPipelineConfig:
        self.session.add(config)
        await self.session.flush()
        return config

    async def get_oje_config(
        self, workspace_id: str, fleet_id: str | None
    ) -> TrustOJEPipelineConfig | None:
        if fleet_id is not None:
            result = await self.session.execute(
                select(TrustOJEPipelineConfig).where(
                    TrustOJEPipelineConfig.workspace_id == workspace_id,
                    TrustOJEPipelineConfig.fleet_id == fleet_id,
                    TrustOJEPipelineConfig.is_active.is_(True),
                )
            )
            item = result.scalar_one_or_none()
            if item is not None:
                return item
        result = await self.session.execute(
            select(TrustOJEPipelineConfig).where(
                TrustOJEPipelineConfig.workspace_id == workspace_id,
                TrustOJEPipelineConfig.fleet_id.is_(None),
                TrustOJEPipelineConfig.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_oje_config_by_id(self, config_id: UUID) -> TrustOJEPipelineConfig | None:
        result = await self.session.execute(
            select(TrustOJEPipelineConfig).where(TrustOJEPipelineConfig.id == config_id)
        )
        return result.scalar_one_or_none()

    async def list_oje_configs(self, workspace_id: str) -> list[TrustOJEPipelineConfig]:
        result = await self.session.execute(
            select(TrustOJEPipelineConfig)
            .where(TrustOJEPipelineConfig.workspace_id == workspace_id)
            .order_by(TrustOJEPipelineConfig.created_at.desc())
        )
        return list(result.scalars().all())

    async def deactivate_oje_config(self, config_id: UUID) -> TrustOJEPipelineConfig | None:
        config = await self.get_oje_config_by_id(config_id)
        if config is None:
            return None
        config.is_active = False
        await self.session.flush()
        return config

    async def create_circuit_breaker_config(
        self,
        config: TrustCircuitBreakerConfig,
    ) -> TrustCircuitBreakerConfig:
        self.session.add(config)
        await self.session.flush()
        return config

    async def list_circuit_breaker_configs(
        self, workspace_id: str
    ) -> list[TrustCircuitBreakerConfig]:
        result = await self.session.execute(
            select(TrustCircuitBreakerConfig)
            .where(TrustCircuitBreakerConfig.workspace_id == workspace_id)
            .order_by(TrustCircuitBreakerConfig.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_circuit_breaker_config(
        self,
        *,
        workspace_id: str,
        agent_id: str | None = None,
        fleet_id: str | None = None,
    ) -> TrustCircuitBreakerConfig | None:
        if agent_id is not None:
            result = await self.session.execute(
                select(TrustCircuitBreakerConfig).where(
                    TrustCircuitBreakerConfig.workspace_id == workspace_id,
                    TrustCircuitBreakerConfig.agent_id == agent_id,
                    TrustCircuitBreakerConfig.enabled.is_(True),
                )
            )
            item = result.scalar_one_or_none()
            if item is not None:
                return item
        if fleet_id is not None:
            result = await self.session.execute(
                select(TrustCircuitBreakerConfig).where(
                    TrustCircuitBreakerConfig.workspace_id == workspace_id,
                    TrustCircuitBreakerConfig.fleet_id == fleet_id,
                    TrustCircuitBreakerConfig.enabled.is_(True),
                )
            )
            item = result.scalar_one_or_none()
            if item is not None:
                return item
        result = await self.session.execute(
            select(TrustCircuitBreakerConfig).where(
                TrustCircuitBreakerConfig.workspace_id == workspace_id,
                TrustCircuitBreakerConfig.agent_id.is_(None),
                TrustCircuitBreakerConfig.fleet_id.is_(None),
                TrustCircuitBreakerConfig.enabled.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_circuit_breaker_config_by_id(
        self,
        config_id: UUID,
    ) -> TrustCircuitBreakerConfig | None:
        result = await self.session.execute(
            select(TrustCircuitBreakerConfig).where(TrustCircuitBreakerConfig.id == config_id)
        )
        return result.scalar_one_or_none()

    async def upsert_circuit_breaker_config(
        self,
        *,
        workspace_id: str,
        agent_id: str | None,
        fleet_id: str | None,
        failure_threshold: int,
        time_window_seconds: int,
        tripped_ttl_seconds: int,
        enabled: bool,
    ) -> TrustCircuitBreakerConfig:
        result = await self.session.execute(
            select(TrustCircuitBreakerConfig).where(
                TrustCircuitBreakerConfig.workspace_id == workspace_id,
                TrustCircuitBreakerConfig.agent_id == agent_id,
                TrustCircuitBreakerConfig.fleet_id == fleet_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            existing = TrustCircuitBreakerConfig(
                workspace_id=workspace_id,
                agent_id=agent_id,
                fleet_id=fleet_id,
                failure_threshold=failure_threshold,
                time_window_seconds=time_window_seconds,
                tripped_ttl_seconds=tripped_ttl_seconds,
                enabled=enabled,
            )
            self.session.add(existing)
        else:
            existing.failure_threshold = failure_threshold
            existing.time_window_seconds = time_window_seconds
            existing.tripped_ttl_seconds = tripped_ttl_seconds
            existing.enabled = enabled
        await self.session.flush()
        return existing

    async def create_rule_set(
        self,
        rule_set: TrustSafetyPreScreenerRuleSet,
    ) -> TrustSafetyPreScreenerRuleSet:
        self.session.add(rule_set)
        await self.session.flush()
        return rule_set

    async def get_rule_set(self, rule_set_id: UUID) -> TrustSafetyPreScreenerRuleSet | None:
        result = await self.session.execute(
            select(TrustSafetyPreScreenerRuleSet).where(
                TrustSafetyPreScreenerRuleSet.id == rule_set_id
            )
        )
        return result.scalar_one_or_none()

    async def get_rule_set_by_version(self, version: int) -> TrustSafetyPreScreenerRuleSet | None:
        result = await self.session.execute(
            select(TrustSafetyPreScreenerRuleSet).where(
                TrustSafetyPreScreenerRuleSet.version == version
            )
        )
        return result.scalar_one_or_none()

    async def get_active_prescreener_rule_set(self) -> TrustSafetyPreScreenerRuleSet | None:
        result = await self.session.execute(
            select(TrustSafetyPreScreenerRuleSet).where(
                TrustSafetyPreScreenerRuleSet.is_active.is_(True)
            )
        )
        return result.scalar_one_or_none()

    async def list_rule_sets(self) -> list[TrustSafetyPreScreenerRuleSet]:
        result = await self.session.execute(
            select(TrustSafetyPreScreenerRuleSet).order_by(
                TrustSafetyPreScreenerRuleSet.version.desc()
            )
        )
        return list(result.scalars().all())

    async def next_rule_set_version(self) -> int:
        result = await self.session.scalar(select(func.max(TrustSafetyPreScreenerRuleSet.version)))
        return int(result or 0) + 1

    async def set_active_rule_set(self, rule_set_id: UUID) -> TrustSafetyPreScreenerRuleSet:
        active = await self.list_rule_sets()
        target: TrustSafetyPreScreenerRuleSet | None = None
        for item in active:
            item.is_active = item.id == rule_set_id
            if item.id == rule_set_id:
                item.activated_at = datetime.now(UTC)
                target = item
        if target is None:
            raise LookupError(str(rule_set_id))
        await self.session.flush()
        return target

    async def count_guardrail_evaluations(
        self,
        agent_id: str,
        *,
        since: datetime,
    ) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(TrustSignal)
            .where(
                TrustSignal.agent_id == agent_id,
                or_(
                    TrustSignal.signal_type == "guardrail.allowed",
                    TrustSignal.signal_type == "guardrail.blocked",
                ),
                TrustSignal.created_at >= since,
            )
        )
        return int(total or 0)

    async def count_blocked_actions(
        self,
        agent_id: str,
        *,
        since: datetime,
    ) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(TrustBlockedActionRecord)
            .where(
                TrustBlockedActionRecord.agent_id == agent_id,
                TrustBlockedActionRecord.created_at >= since,
            )
        )
        return int(total or 0)

    async def get_latest_certification_for_agent(self, agent_id: str) -> TrustCertification | None:
        result = await self.session.execute(
            select(TrustCertification)
            .where(TrustCertification.agent_id == agent_id)
            .order_by(TrustCertification.created_at.desc(), TrustCertification.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_expiry_approaching_certifications(
        self,
        *,
        now: datetime,
        within_days: int,
    ) -> list[TrustCertification]:
        threshold = now + timedelta(days=within_days)
        result = await self.session.execute(
            select(TrustCertification).where(
                TrustCertification.status == CertificationStatus.active,
                TrustCertification.expires_at.is_not(None),
                TrustCertification.expires_at <= threshold,
                TrustCertification.expires_at >= now,
            )
        )
        return list(result.scalars().all())
