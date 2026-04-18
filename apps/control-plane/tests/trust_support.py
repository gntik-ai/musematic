from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fnmatch import fnmatch
from platform.common.auth_middleware import AuthMiddleware
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.trust.ate_service import ATEService
from platform.trust.circuit_breaker import CircuitBreakerService
from platform.trust.dependencies import (
    get_ate_service,
    get_certification_service,
    get_circuit_breaker_service,
    get_guardrail_pipeline_service,
    get_oje_service,
    get_prescreener_service,
    get_privacy_assessment_service,
    get_recertification_service,
    get_trust_tier_service,
)
from platform.trust.guardrail_pipeline import GuardrailPipelineService
from platform.trust.models import (
    CertificationStatus,
    GuardrailLayer,
    OJEVerdictType,
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
from platform.trust.oje_pipeline import OJEPipelineService
from platform.trust.prescreener import SafetyPreScreenerService
from platform.trust.privacy_assessment import PrivacyAssessmentService
from platform.trust.recertification import RecertificationService
from platform.trust.router import router as trust_router
from platform.trust.schemas import (
    ATEConfigCreate,
    CertificationCreate,
    CircuitBreakerConfigCreate,
    GuardrailPipelineConfigCreate,
    OJEPipelineConfigCreate,
    PreScreenerRuleDefinition,
    PreScreenerRuleSetCreate,
)
from platform.trust.service import CertificationService
from platform.trust.trust_tier import TrustTierService
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI

from tests.auth_support import RecordingProducer, role_claim


def build_trust_settings(**overrides: Any) -> PlatformSettings:
    values: dict[str, Any] = {
        "AUTH_JWT_SECRET_KEY": "trust-secret",
        "AUTH_JWT_ALGORITHM": "HS256",
        "TRUST_DEFAULT_WORKSPACE_ID": "00000000-0000-0000-0000-000000000001",
    }
    values.update(overrides)
    return PlatformSettings(**values)


def stamp(model: Any, *, created_at: datetime | None = None) -> Any:
    now = created_at or datetime.now(UTC)
    if getattr(model, "id", None) is None:
        model.id = uuid4()
    if getattr(model, "created_at", None) is None:
        model.created_at = now
    if getattr(model, "updated_at", None) is None:
        model.updated_at = now
    return model


class SessionStub:
    def __init__(self) -> None:
        self.flush_count = 0

    async def flush(self) -> None:
        self.flush_count += 1


@dataclass
class InMemoryTrustRepository:
    session: SessionStub = field(default_factory=SessionStub)
    certifications: list[TrustCertification] = field(default_factory=list)
    evidence_refs: list[TrustCertificationEvidenceRef] = field(default_factory=list)
    tiers: list[TrustTier] = field(default_factory=list)
    signals: list[TrustSignal] = field(default_factory=list)
    proof_links: list[TrustProofLink] = field(default_factory=list)
    triggers: list[TrustRecertificationTrigger] = field(default_factory=list)
    blocked_actions: list[TrustBlockedActionRecord] = field(default_factory=list)
    ate_configs: list[TrustATEConfiguration] = field(default_factory=list)
    guardrail_configs: list[TrustGuardrailPipelineConfig] = field(default_factory=list)
    oje_configs: list[TrustOJEPipelineConfig] = field(default_factory=list)
    circuit_breaker_configs: list[TrustCircuitBreakerConfig] = field(default_factory=list)
    rule_sets: list[TrustSafetyPreScreenerRuleSet] = field(default_factory=list)

    async def create_certification(self, certification: TrustCertification) -> TrustCertification:
        certification.evidence_refs = list(getattr(certification, "evidence_refs", []))
        stamp(certification)
        self.certifications.append(certification)
        await self.session.flush()
        return certification

    async def get_certification(self, certification_id: UUID) -> TrustCertification | None:
        return next((item for item in self.certifications if item.id == certification_id), None)

    async def list_certifications_for_agent(self, agent_id: str) -> list[TrustCertification]:
        return sorted(
            [item for item in self.certifications if item.agent_id == agent_id],
            key=lambda item: (item.created_at, item.id),
            reverse=True,
        )

    async def list_active_certifications_for_agent(self, agent_id: str) -> list[TrustCertification]:
        return [
            item
            for item in self.certifications
            if item.agent_id == agent_id and item.status == CertificationStatus.active
        ]

    async def list_stale_certifications(self, now: datetime) -> list[TrustCertification]:
        return [
            item
            for item in self.certifications
            if item.status == CertificationStatus.active
            and item.expires_at is not None
            and item.expires_at < now
        ]

    async def get_latest_certification_for_agent(self, agent_id: str) -> TrustCertification | None:
        certifications = await self.list_certifications_for_agent(agent_id)
        return certifications[0] if certifications else None

    async def list_expiry_approaching_certifications(
        self,
        *,
        now: datetime,
        within_days: int,
    ) -> list[TrustCertification]:
        threshold = now + timedelta(days=within_days)
        return [
            item
            for item in self.certifications
            if item.status == CertificationStatus.active
            and item.expires_at is not None
            and now <= item.expires_at <= threshold
        ]

    async def create_evidence_ref(
        self,
        evidence_ref: TrustCertificationEvidenceRef,
    ) -> TrustCertificationEvidenceRef:
        stamp(evidence_ref)
        self.evidence_refs.append(evidence_ref)
        certification = await self.get_certification(evidence_ref.certification_id)
        if certification is not None:
            certification.evidence_refs.append(evidence_ref)
        await self.session.flush()
        return evidence_ref

    async def get_tier(self, agent_id: str) -> TrustTier | None:
        return next((item for item in self.tiers if item.agent_id == agent_id), None)

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
            existing = stamp(
                TrustTier(
                    agent_id=agent_id,
                    agent_fqn=agent_fqn,
                    tier=tier,
                    trust_score=trust_score,
                    certification_component=certification_component,
                    guardrail_component=guardrail_component,
                    behavioral_component=behavioral_component,
                    last_computed_at=last_computed_at,
                )
            )
            self.tiers.append(existing)
        else:
            existing.agent_fqn = agent_fqn
            existing.tier = tier
            existing.trust_score = trust_score
            existing.certification_component = certification_component
            existing.guardrail_component = guardrail_component
            existing.behavioral_component = behavioral_component
            existing.last_computed_at = last_computed_at
            existing.updated_at = datetime.now(UTC)
        await self.session.flush()
        return existing

    async def create_signal(self, signal: TrustSignal) -> TrustSignal:
        stamp(signal)
        self.signals.append(signal)
        await self.session.flush()
        return signal

    async def create_proof_link(self, proof_link: TrustProofLink) -> TrustProofLink:
        stamp(proof_link)
        self.proof_links.append(proof_link)
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
        items = [item for item in self.signals if item.agent_id == agent_id]
        if since is not None:
            items = [item for item in items if item.created_at >= since]
        if signal_type is not None:
            items = [item for item in items if item.signal_type == signal_type]
        items.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        total = len(items)
        return items[offset : offset + limit], total

    async def count_guardrail_evaluations(self, agent_id: str, *, since: datetime) -> int:
        relevant = {
            "guardrail.allowed",
            "guardrail.blocked",
        }
        return sum(
            1
            for item in self.signals
            if item.agent_id == agent_id
            and item.signal_type in relevant
            and item.created_at >= since
        )

    async def count_blocked_actions(self, agent_id: str, *, since: datetime) -> int:
        return sum(
            1
            for item in self.blocked_actions
            if item.agent_id == agent_id and item.created_at >= since
        )

    async def create_trigger(
        self,
        trigger: TrustRecertificationTrigger,
    ) -> TrustRecertificationTrigger:
        stamp(trigger)
        self.triggers.append(trigger)
        await self.session.flush()
        return trigger

    async def get_trigger(self, trigger_id: UUID) -> TrustRecertificationTrigger | None:
        return next((item for item in self.triggers if item.id == trigger_id), None)

    async def get_pending_trigger(
        self,
        *,
        agent_id: str,
        agent_revision_id: str,
        trigger_type: RecertificationTriggerType,
    ) -> TrustRecertificationTrigger | None:
        return next(
            (
                item
                for item in self.triggers
                if item.agent_id == agent_id
                and item.agent_revision_id == agent_revision_id
                and item.trigger_type == trigger_type
                and item.status == RecertificationTriggerStatus.pending
            ),
            None,
        )

    async def list_triggers(
        self,
        *,
        agent_id: str | None = None,
        status: RecertificationTriggerStatus | None = None,
    ) -> list[TrustRecertificationTrigger]:
        items = list(self.triggers)
        if agent_id is not None:
            items = [item for item in items if item.agent_id == agent_id]
        if status is not None:
            items = [item for item in items if item.status == status]
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items

    async def list_pending_triggers(self) -> list[TrustRecertificationTrigger]:
        return await self.list_triggers(status=RecertificationTriggerStatus.pending)

    async def create_blocked_action_record(
        self,
        record: TrustBlockedActionRecord,
    ) -> TrustBlockedActionRecord:
        stamp(record)
        self.blocked_actions.append(record)
        await self.session.flush()
        return record

    async def get_blocked_action(self, record_id: UUID) -> TrustBlockedActionRecord | None:
        return next((item for item in self.blocked_actions if item.id == record_id), None)

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
        items = list(self.blocked_actions)
        if agent_id is not None:
            items = [item for item in items if item.agent_id == agent_id]
        if layer is not None:
            items = [item for item in items if item.layer == layer]
        if workspace_id is not None:
            items = [item for item in items if item.workspace_id == workspace_id]
        if since is not None:
            items = [item for item in items if item.created_at >= since]
        if until is not None:
            items = [item for item in items if item.created_at <= until]
        items.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        total = len(items)
        return items[offset : offset + limit], total

    async def create_ate_config(self, config: TrustATEConfiguration) -> TrustATEConfiguration:
        stamp(config)
        self.ate_configs.append(config)
        await self.session.flush()
        return config

    async def get_ate_config(self, config_id: UUID) -> TrustATEConfiguration | None:
        return next((item for item in self.ate_configs if item.id == config_id), None)

    async def list_ate_configs_for_workspace(
        self,
        workspace_id: str,
    ) -> list[TrustATEConfiguration]:
        return sorted(
            [item for item in self.ate_configs if item.workspace_id == workspace_id],
            key=lambda item: (item.name, item.version, item.created_at),
        )

    async def list_ate_config_versions(
        self,
        workspace_id: str,
        name: str,
    ) -> list[TrustATEConfiguration]:
        return sorted(
            [
                item
                for item in self.ate_configs
                if item.workspace_id == workspace_id and item.name == name
            ],
            key=lambda item: item.version,
            reverse=True,
        )

    async def get_latest_ate_config_version(self, workspace_id: str, name: str) -> int:
        versions = await self.list_ate_config_versions(workspace_id, name)
        return versions[0].version if versions else 0

    async def deactivate_ate_configs(self, workspace_id: str, name: str) -> None:
        for item in await self.list_ate_config_versions(workspace_id, name):
            item.is_active = False
        await self.session.flush()

    async def create_guardrail_config(
        self,
        config: TrustGuardrailPipelineConfig,
    ) -> TrustGuardrailPipelineConfig:
        stamp(config)
        self.guardrail_configs.append(config)
        await self.session.flush()
        return config

    async def list_guardrail_configs(
        self,
        workspace_id: str,
    ) -> list[TrustGuardrailPipelineConfig]:
        return [item for item in self.guardrail_configs if item.workspace_id == workspace_id]

    async def get_guardrail_config(
        self,
        workspace_id: str,
        fleet_id: str | None = None,
    ) -> TrustGuardrailPipelineConfig | None:
        if fleet_id is not None:
            item = next(
                (
                    config
                    for config in self.guardrail_configs
                    if config.workspace_id == workspace_id
                    and config.fleet_id == fleet_id
                    and config.is_active
                ),
                None,
            )
            if item is not None:
                return item
        return next(
            (
                config
                for config in self.guardrail_configs
                if config.workspace_id == workspace_id
                and config.fleet_id is None
                and config.is_active
            ),
            None,
        )

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
            existing.updated_at = datetime.now(UTC)
            await self.session.flush()
            return existing
        created = TrustGuardrailPipelineConfig(
            workspace_id=workspace_id,
            fleet_id=fleet_id,
            config=config,
            is_active=is_active,
        )
        return await self.create_guardrail_config(created)

    async def create_oje_config(self, config: TrustOJEPipelineConfig) -> TrustOJEPipelineConfig:
        stamp(config)
        self.oje_configs.append(config)
        await self.session.flush()
        return config

    async def get_oje_config(
        self,
        workspace_id: str,
        fleet_id: str | None,
    ) -> TrustOJEPipelineConfig | None:
        if fleet_id is not None:
            item = next(
                (
                    config
                    for config in self.oje_configs
                    if config.workspace_id == workspace_id
                    and config.fleet_id == fleet_id
                    and config.is_active
                ),
                None,
            )
            if item is not None:
                return item
        return next(
            (
                config
                for config in self.oje_configs
                if config.workspace_id == workspace_id
                and config.fleet_id is None
                and config.is_active
            ),
            None,
        )

    async def get_oje_config_by_id(self, config_id: UUID) -> TrustOJEPipelineConfig | None:
        return next((item for item in self.oje_configs if item.id == config_id), None)

    async def list_oje_configs(self, workspace_id: str) -> list[TrustOJEPipelineConfig]:
        return [item for item in self.oje_configs if item.workspace_id == workspace_id]

    async def deactivate_oje_config(self, config_id: UUID) -> TrustOJEPipelineConfig | None:
        item = await self.get_oje_config_by_id(config_id)
        if item is not None:
            item.is_active = False
            item.updated_at = datetime.now(UTC)
        return item

    async def list_circuit_breaker_configs(
        self,
        workspace_id: str,
    ) -> list[TrustCircuitBreakerConfig]:
        return [item for item in self.circuit_breaker_configs if item.workspace_id == workspace_id]

    async def get_circuit_breaker_config(
        self,
        *,
        workspace_id: str,
        agent_id: str | None = None,
        fleet_id: str | None = None,
    ) -> TrustCircuitBreakerConfig | None:
        if agent_id is not None:
            item = next(
                (
                    config
                    for config in self.circuit_breaker_configs
                    if config.workspace_id == workspace_id
                    and config.agent_id == agent_id
                    and config.enabled
                ),
                None,
            )
            if item is not None:
                return item
        if fleet_id is not None:
            item = next(
                (
                    config
                    for config in self.circuit_breaker_configs
                    if config.workspace_id == workspace_id
                    and config.fleet_id == fleet_id
                    and config.enabled
                ),
                None,
            )
            if item is not None:
                return item
        return next(
            (
                config
                for config in self.circuit_breaker_configs
                if config.workspace_id == workspace_id
                and config.agent_id is None
                and config.fleet_id is None
                and config.enabled
            ),
            None,
        )

    async def get_circuit_breaker_config_by_id(
        self,
        config_id: UUID,
    ) -> TrustCircuitBreakerConfig | None:
        return next((item for item in self.circuit_breaker_configs if item.id == config_id), None)

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
        existing = next(
            (
                item
                for item in self.circuit_breaker_configs
                if item.workspace_id == workspace_id
                and item.agent_id == agent_id
                and item.fleet_id == fleet_id
            ),
            None,
        )
        if existing is None:
            existing = stamp(
                TrustCircuitBreakerConfig(
                    workspace_id=workspace_id,
                    agent_id=agent_id,
                    fleet_id=fleet_id,
                    failure_threshold=failure_threshold,
                    time_window_seconds=time_window_seconds,
                    tripped_ttl_seconds=tripped_ttl_seconds,
                    enabled=enabled,
                )
            )
            self.circuit_breaker_configs.append(existing)
        else:
            existing.failure_threshold = failure_threshold
            existing.time_window_seconds = time_window_seconds
            existing.tripped_ttl_seconds = tripped_ttl_seconds
            existing.enabled = enabled
            existing.updated_at = datetime.now(UTC)
        await self.session.flush()
        return existing

    async def create_rule_set(
        self,
        rule_set: TrustSafetyPreScreenerRuleSet,
    ) -> TrustSafetyPreScreenerRuleSet:
        stamp(rule_set)
        self.rule_sets.append(rule_set)
        await self.session.flush()
        return rule_set

    async def get_rule_set(
        self,
        rule_set_id: UUID,
    ) -> TrustSafetyPreScreenerRuleSet | None:
        return next((item for item in self.rule_sets if item.id == rule_set_id), None)

    async def get_rule_set_by_version(
        self,
        version: int,
    ) -> TrustSafetyPreScreenerRuleSet | None:
        return next((item for item in self.rule_sets if item.version == version), None)

    async def get_active_prescreener_rule_set(self) -> TrustSafetyPreScreenerRuleSet | None:
        return next((item for item in self.rule_sets if item.is_active), None)

    async def list_rule_sets(self) -> list[TrustSafetyPreScreenerRuleSet]:
        return sorted(self.rule_sets, key=lambda item: item.version, reverse=True)

    async def next_rule_set_version(self) -> int:
        return max((item.version for item in self.rule_sets), default=0) + 1

    async def set_active_rule_set(
        self,
        rule_set_id: UUID,
    ) -> TrustSafetyPreScreenerRuleSet:
        target = await self.get_rule_set(rule_set_id)
        if target is None:
            raise LookupError(str(rule_set_id))
        for item in self.rule_sets:
            item.is_active = item.id == rule_set_id
            if item.id == rule_set_id:
                item.activated_at = datetime.now(UTC)
        await self.session.flush()
        return target


@dataclass
class FakeObjectStorage:
    buckets: set[str] = field(default_factory=set)
    objects: dict[tuple[str, str], bytes] = field(default_factory=dict)

    async def create_bucket_if_not_exists(self, bucket: str) -> None:
        self.buckets.add(bucket)

    async def upload_object(
        self,
        bucket: str,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> None:
        del content_type
        self.buckets.add(bucket)
        self.objects[(bucket, key)] = data

    async def download_object(self, bucket: str, key: str) -> bytes:
        return self.objects[(bucket, key)]


@dataclass
class FakeTrustRedisClient:
    strings: dict[str, bytes] = field(default_factory=dict)
    expirations: dict[str, int] = field(default_factory=dict)
    sorted_sets: dict[str, list[str]] = field(default_factory=dict)
    _script_sha: str = "trust-cb-sha"
    script_loads: list[str] = field(default_factory=list)
    evalsha_calls: list[tuple[Any, ...]] = field(default_factory=list)
    _url: str = "redis://localhost:6379"

    def __post_init__(self) -> None:
        self.client = self

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def health_check(self) -> bool:
        return True

    async def get(self, key: str) -> bytes | None:
        return self.strings.get(key)

    async def set(
        self,
        key: str,
        value: bytes | str,
        ttl: int | None = None,
        ex: int | None = None,
    ) -> None:
        encoded = value if isinstance(value, bytes) else str(value).encode("utf-8")
        self.strings[key] = encoded
        expiry = ttl if ttl is not None else ex
        if expiry is not None:
            self.expirations[key] = expiry

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.strings.pop(key, None)
            self.expirations.pop(key, None)
            self.sorted_sets.pop(key, None)

    async def scan(
        self,
        *,
        cursor: int,
        match: str,
        count: int,
    ) -> tuple[int, list[str]]:
        del count
        keys = [key for key in self.strings if fnmatch(key, match)]
        return 0 if cursor == 0 else cursor, keys if cursor == 0 else []

    async def script_load(self, script: str) -> str:
        self.script_loads.append(script)
        return self._script_sha

    async def evalsha(self, sha: str, numkeys: int, *args: Any) -> list[int]:
        del numkeys
        self.evalsha_calls.append((sha, *args))
        return await self._run_circuit_breaker(*args)

    async def eval(self, script: str, numkeys: int, *args: Any) -> list[int]:
        del script, numkeys
        return await self._run_circuit_breaker(*args)

    async def zcard(self, key: str) -> int:
        return len(self.sorted_sets.get(key, []))

    async def _run_circuit_breaker(
        self,
        failures_key: str,
        tripped_key: str,
        threshold: int,
        window_seconds: int,
        tripped_ttl: int,
    ) -> list[int]:
        del window_seconds
        members = self.sorted_sets.setdefault(failures_key, [])
        members.append(f"{len(members) + 1}")
        count = len(members)
        tripped = int(count >= int(threshold))
        if tripped:
            await self.set(tripped_key, b"1", ttl=int(tripped_ttl))
        return [count, tripped]


@dataclass
class PolicyEngineStub:
    tool_result: Any = True
    memory_result: Any = True
    privacy_result: Any = True
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    memory_calls: list[dict[str, Any]] = field(default_factory=list)
    privacy_calls: list[dict[str, Any]] = field(default_factory=list)

    async def evaluate_tool_access(self, **kwargs: Any) -> Any:
        self.tool_calls.append(kwargs)
        return self.tool_result

    async def evaluate_memory_write(self, **kwargs: Any) -> Any:
        self.memory_calls.append(kwargs)
        return self.memory_result

    async def check_privacy_compliance(self, **kwargs: Any) -> Any:
        self.privacy_calls.append(kwargs)
        return self.privacy_result


@dataclass
class RuntimeControllerStub:
    stop_calls: list[dict[str, Any]] = field(default_factory=list)
    pause_calls: list[dict[str, Any]] = field(default_factory=list)

    async def stop_runtime(self, runtime_id: str | None, *, reason: str) -> None:
        self.stop_calls.append({"runtime_id": runtime_id, "reason": reason})

    async def pause_workflow(self, execution_id: str, *, reason: str) -> None:
        self.pause_calls.append({"execution_id": execution_id, "reason": reason})


@dataclass
class SimulationControllerStub:
    result: dict[str, Any] = field(default_factory=lambda: {"simulation_id": "sim-001"})
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def create_simulation(self, *, config: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(config)
        return dict(self.result)


@dataclass
class RegistryServiceStub:
    known_fqns: set[str] = field(default_factory=set)

    async def get_agent_by_fqn(self, workspace_id: UUID, fqn: str) -> dict[str, str] | None:
        del workspace_id
        return {"fqn": fqn} if fqn in self.known_fqns else None


@dataclass
class InteractionsServiceStub:
    verdict: dict[str, Any] | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def invoke_trust_judge(
        self,
        judge_fqns: list[str],
        signal: dict[str, Any],
        *,
        trust_pipeline_context: bool,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "judge_fqns": list(judge_fqns),
                "signal": signal,
                "trust_pipeline_context": trust_pipeline_context,
            }
        )
        if self.verdict is not None:
            return dict(self.verdict)
        return {
            "pipeline_config_id": str(uuid4()),
            "observer_signal_id": str(signal.get("signal_id") or uuid4()),
            "judge_fqn": judge_fqns[0],
            "verdict": OJEVerdictType.compliant,
            "reasoning": "ok",
            "policy_basis": "policy:default",
            "enforcer_action_taken": None,
        }


@dataclass
class TrustServiceBundle:
    settings: PlatformSettings
    repository: InMemoryTrustRepository
    producer: RecordingProducer
    redis: FakeTrustRedisClient
    object_storage: FakeObjectStorage
    policy_engine: PolicyEngineStub
    runtime_controller: RuntimeControllerStub
    simulation_controller: SimulationControllerStub
    registry_service: RegistryServiceStub
    interactions_service: InteractionsServiceStub
    certification_service: CertificationService
    trust_tier_service: TrustTierService
    guardrail_service: GuardrailPipelineService
    prescreener_service: SafetyPreScreenerService
    oje_service: OJEPipelineService
    recertification_service: RecertificationService
    circuit_breaker_service: CircuitBreakerService
    ate_service: ATEService
    privacy_service: PrivacyAssessmentService


def build_trust_bundle(**settings_overrides: Any) -> TrustServiceBundle:
    settings = build_trust_settings(**settings_overrides)
    repository = InMemoryTrustRepository()
    producer = RecordingProducer()
    redis = FakeTrustRedisClient()
    object_storage = FakeObjectStorage()
    policy_engine = PolicyEngineStub()
    runtime_controller = RuntimeControllerStub()
    simulation_controller = SimulationControllerStub()
    registry_service = RegistryServiceStub()
    interactions_service = InteractionsServiceStub()
    certification_service = CertificationService(
        repository=repository,
        settings=settings,
        producer=producer,
    )
    trust_tier_service = TrustTierService(
        repository=repository,
        settings=settings,
        producer=producer,
    )
    prescreener_service = SafetyPreScreenerService(
        repository=repository,
        settings=settings,
        redis_client=redis,
        object_storage=object_storage,
        producer=producer,
    )
    guardrail_service = GuardrailPipelineService(
        repository=repository,
        settings=settings,
        producer=producer,
        policy_engine=policy_engine,
        pre_screener=prescreener_service,
    )
    oje_service = OJEPipelineService(
        repository=repository,
        settings=settings,
        producer=producer,
        registry_service=registry_service,
        interactions_service=interactions_service,
        runtime_controller=runtime_controller,
    )
    recertification_service = RecertificationService(
        repository=repository,
        settings=settings,
        producer=producer,
    )
    circuit_breaker_service = CircuitBreakerService(
        repository=repository,
        settings=settings,
        producer=producer,
        redis_client=redis,
        runtime_controller=runtime_controller,
    )
    ate_service = ATEService(
        repository=repository,
        settings=settings,
        object_storage=object_storage,
        simulation_controller=simulation_controller,
        redis_client=redis,
    )
    privacy_service = PrivacyAssessmentService(policy_engine=policy_engine)
    return TrustServiceBundle(
        settings=settings,
        repository=repository,
        producer=producer,
        redis=redis,
        object_storage=object_storage,
        policy_engine=policy_engine,
        runtime_controller=runtime_controller,
        simulation_controller=simulation_controller,
        registry_service=registry_service,
        interactions_service=interactions_service,
        certification_service=certification_service,
        trust_tier_service=trust_tier_service,
        guardrail_service=guardrail_service,
        prescreener_service=prescreener_service,
        oje_service=oje_service,
        recertification_service=recertification_service,
        circuit_breaker_service=circuit_breaker_service,
        ate_service=ate_service,
        privacy_service=privacy_service,
    )


def build_trust_app(
    *,
    bundle: TrustServiceBundle | None = None,
    current_user: dict[str, Any] | None = None,
    require_auth_middleware: bool = False,
) -> tuple[FastAPI, TrustServiceBundle]:
    resolved_bundle = bundle or build_trust_bundle()
    app = FastAPI()
    app.state.settings = resolved_bundle.settings
    app.state.clients = {
        "redis": resolved_bundle.redis,
        "kafka": resolved_bundle.producer,
        "minio": resolved_bundle.object_storage,
        "runtime_controller": resolved_bundle.runtime_controller,
        "simulation_controller": resolved_bundle.simulation_controller,
    }
    app.add_exception_handler(PlatformError, platform_exception_handler)
    if require_auth_middleware:
        app.add_middleware(AuthMiddleware)
    app.dependency_overrides[get_certification_service] = lambda: (
        resolved_bundle.certification_service
    )
    app.dependency_overrides[get_trust_tier_service] = lambda: resolved_bundle.trust_tier_service
    app.dependency_overrides[get_guardrail_pipeline_service] = lambda: (
        resolved_bundle.guardrail_service
    )
    app.dependency_overrides[get_prescreener_service] = lambda: resolved_bundle.prescreener_service
    app.dependency_overrides[get_oje_service] = lambda: resolved_bundle.oje_service
    app.dependency_overrides[get_recertification_service] = lambda: (
        resolved_bundle.recertification_service
    )
    app.dependency_overrides[get_circuit_breaker_service] = lambda: (
        resolved_bundle.circuit_breaker_service
    )
    app.dependency_overrides[get_ate_service] = lambda: resolved_bundle.ate_service
    app.dependency_overrides[get_privacy_assessment_service] = lambda: (
        resolved_bundle.privacy_service
    )
    if current_user is not None:

        async def _current_user() -> dict[str, Any]:
            return current_user

        app.dependency_overrides[get_current_user] = _current_user
    app.include_router(trust_router, prefix="/api/v1/trust")
    return app, resolved_bundle


def admin_user() -> dict[str, Any]:
    return {
        "sub": str(uuid4()),
        "roles": [role_claim("platform_admin")],
        "type": "human",
    }


def trust_certifier_user() -> dict[str, Any]:
    return {
        "sub": str(uuid4()),
        "roles": [role_claim("trust_certifier"), role_claim("platform_admin")],
        "type": "human",
    }


def workspace_member_user() -> dict[str, Any]:
    return {
        "sub": str(uuid4()),
        "roles": [role_claim("workspace_member"), role_claim("workspace_admin")],
        "type": "human",
    }


def service_account_user() -> dict[str, Any]:
    return {
        "sub": str(uuid4()),
        "roles": [role_claim("service_account")],
        "type": "service",
    }


def build_certification(
    *,
    agent_id: str = "agent-1",
    agent_fqn: str = "fleet:agent-1",
    agent_revision_id: str = "rev-1",
    status: CertificationStatus = CertificationStatus.pending,
    expires_at: datetime | None = None,
) -> TrustCertification:
    return stamp(
        TrustCertification(
            agent_id=agent_id,
            agent_fqn=agent_fqn,
            agent_revision_id=agent_revision_id,
            status=status,
            issued_by="tester",
            expires_at=expires_at,
        )
    )


def build_signal(
    *,
    agent_id: str = "agent-1",
    signal_type: str = "behavioral_conformance",
    score_contribution: Decimal = Decimal("1.0000"),
    source_id: str = "source-1",
    created_at: datetime | None = None,
) -> TrustSignal:
    return stamp(
        TrustSignal(
            agent_id=agent_id,
            signal_type=signal_type,
            score_contribution=score_contribution,
            source_type="test",
            source_id=source_id,
            workspace_id="workspace-1",
        ),
        created_at=created_at,
    )


def build_rule_set_create() -> PreScreenerRuleSetCreate:
    return PreScreenerRuleSetCreate(
        name="default",
        description="default rules",
        rules=[
            PreScreenerRuleDefinition(name="jailbreak", pattern="jailbreak"),
            PreScreenerRuleDefinition(name="drop-table", pattern="drop\\s+table"),
        ],
    )


def build_ate_config_create() -> ATEConfigCreate:
    return ATEConfigCreate(
        name="smoke",
        description="smoke suite",
        test_scenarios=[{"summary": "Scenario A"}],
        scoring_config={"min_score": 0.9},
        timeout_seconds=120,
    )


def build_guardrail_config_create() -> GuardrailPipelineConfigCreate:
    return GuardrailPipelineConfigCreate(
        workspace_id="workspace-1",
        fleet_id=None,
        config={"action_commit": {"enabled": True}},
        is_active=True,
    )


def build_oje_config_create() -> OJEPipelineConfigCreate:
    return OJEPipelineConfigCreate(
        workspace_id="00000000-0000-0000-0000-000000000001",
        fleet_id=None,
        observer_fqns=["observer:one"],
        judge_fqns=["judge:one"],
        enforcer_fqns=["enforcer:one"],
        policy_refs=["policy:one"],
        is_active=True,
    )


def build_circuit_breaker_config_create() -> CircuitBreakerConfigCreate:
    return CircuitBreakerConfigCreate(
        workspace_id="00000000-0000-0000-0000-000000000001",
        agent_id="agent-1",
        failure_threshold=2,
        time_window_seconds=600,
        tripped_ttl_seconds=3600,
        enabled=True,
    )


def build_certification_create() -> CertificationCreate:
    return CertificationCreate(
        agent_id="agent-1",
        agent_fqn="fleet:agent-1",
        agent_revision_id="rev-1",
    )
