from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.trust.models import (
    CertificationStatus,
    GuardrailLayer,
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
                TrustCertification.status == CertificationStatus.active,
                TrustCertification.expires_at.is_not(None),
                TrustCertification.expires_at < now,
            )
        )
        return list(result.scalars().all())

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
