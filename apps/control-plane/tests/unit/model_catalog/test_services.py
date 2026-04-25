from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.common.exceptions import AuthorizationError, NotFoundError, ValidationError
from platform.model_catalog.models import (
    InjectionDefensePattern,
    ModelCard,
    ModelCatalogEntry,
    ModelFallbackPolicy,
    ModelProviderCredential,
)
from platform.model_catalog.schemas import (
    BlockRequest,
    CatalogEntryCreate,
    CatalogEntryPatch,
    CredentialCreate,
    CredentialRotateRequest,
    DeprecateRequest,
    FallbackPolicyCreate,
    FallbackPolicyPatch,
    InjectionPatternCreate,
    InjectionPatternPatch,
    ModelCardFields,
    ReapproveRequest,
)
from platform.model_catalog.services.catalog_service import CatalogService
from platform.model_catalog.services.credential_service import CredentialService
from platform.model_catalog.services.fallback_service import FallbackPolicyService
from platform.model_catalog.services.injection_defense_service import InjectionDefenseService
from platform.model_catalog.services.model_card_service import ModelCardService
from platform.model_catalog.workers.auto_deprecation_scanner import run_auto_deprecation_scan
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest


class SessionStub:
    def __init__(self) -> None:
        self.flush_count = 0
        self.deleted: list[object] = []

    async def flush(self) -> None:
        self.flush_count += 1

    async def delete(self, item: object) -> None:
        self.deleted.append(item)


class RepositoryStub:
    def __init__(self) -> None:
        self.session = SessionStub()
        self.entries: dict[UUID, ModelCatalogEntry] = {}
        self.cards: dict[UUID, ModelCard] = {}
        self.policies: dict[UUID, ModelFallbackPolicy] = {}
        self.credentials: dict[UUID, ModelProviderCredential] = {}
        self.patterns: dict[UUID, InjectionDefensePattern] = {}

    async def add(self, item: object) -> object:
        if isinstance(item, ModelCatalogEntry):
            item.id = item.id or uuid4()
            self.entries[item.id] = item
        elif isinstance(item, ModelCard):
            item.id = item.id or uuid4()
            self.cards[item.catalog_entry_id] = item
        elif isinstance(item, ModelFallbackPolicy):
            item.id = item.id or uuid4()
            self.policies[item.id] = item
        elif isinstance(item, ModelProviderCredential):
            item.id = item.id or uuid4()
            self.credentials[item.id] = item
        elif isinstance(item, InjectionDefensePattern):
            item.id = item.id or uuid4()
            item.seeded = bool(item.seeded)
            self.patterns[item.id] = item
        await self.session.flush()
        return item

    async def get_entry(self, entry_id: UUID) -> ModelCatalogEntry | None:
        return self.entries.get(entry_id)

    async def get_entry_by_provider_model(
        self,
        provider: str,
        model_id: str,
    ) -> ModelCatalogEntry | None:
        return next(
            (
                entry
                for entry in self.entries.values()
                if entry.provider == provider and entry.model_id == model_id
            ),
            None,
        )

    async def list_entries(
        self,
        *,
        provider: str | None = None,
        status: str | None = None,
    ) -> list[ModelCatalogEntry]:
        return [
            entry
            for entry in self.entries.values()
            if (provider is None or entry.provider == provider)
            and (status is None or entry.status == status)
        ]

    async def list_expired_approved_entries(
        self,
        *,
        now: datetime | None = None,
    ) -> list[ModelCatalogEntry]:
        cutoff = now or datetime.now(UTC)
        return [
            entry
            for entry in self.entries.values()
            if entry.status == "approved" and entry.approval_expires_at < cutoff
        ]

    async def list_entries_missing_cards(
        self,
        *,
        older_than_days: int = 7,
    ) -> list[ModelCatalogEntry]:
        del older_than_days
        return [
            entry
            for entry in self.entries.values()
            if entry.status == "approved" and entry.id not in self.cards
        ]

    async def get_card_by_entry_id(self, entry_id: UUID) -> ModelCard | None:
        return self.cards.get(entry_id)

    async def list_card_history(self, entry_id: UUID) -> list[ModelCard]:
        card = self.cards.get(entry_id)
        return [] if card is None else [card]

    async def get_fallback_policy(self, policy_id: UUID) -> ModelFallbackPolicy | None:
        return self.policies.get(policy_id)

    async def list_fallback_policies(
        self,
        *,
        primary_model_id: UUID | None = None,
        scope_type: str | None = None,
    ) -> list[ModelFallbackPolicy]:
        return [
            policy
            for policy in self.policies.values()
            if (primary_model_id is None or policy.primary_model_id == primary_model_id)
            and (scope_type is None or policy.scope_type == scope_type)
        ]

    async def get_fallback_policy_for_scope(
        self,
        *,
        scope_type: str,
        scope_id: UUID | None,
        primary_model_id: UUID,
    ) -> ModelFallbackPolicy | None:
        return next(
            (
                policy
                for policy in self.policies.values()
                if policy.scope_type == scope_type
                and policy.scope_id == scope_id
                and policy.primary_model_id == primary_model_id
            ),
            None,
        )

    async def delete_fallback_policy(self, policy: ModelFallbackPolicy) -> None:
        self.policies.pop(policy.id, None)
        await self.session.delete(policy)

    async def get_credential_by_workspace_provider(
        self,
        workspace_id: UUID,
        provider: str,
    ) -> ModelProviderCredential | None:
        return next(
            (
                credential
                for credential in self.credentials.values()
                if credential.workspace_id == workspace_id and credential.provider == provider
            ),
            None,
        )

    async def get_credential(self, credential_id: UUID) -> ModelProviderCredential | None:
        return self.credentials.get(credential_id)

    async def list_credentials(
        self,
        *,
        workspace_id: UUID | None = None,
        provider: str | None = None,
    ) -> list[ModelProviderCredential]:
        return [
            credential
            for credential in self.credentials.values()
            if (workspace_id is None or credential.workspace_id == workspace_id)
            and (provider is None or credential.provider == provider)
        ]

    async def delete_credential(self, credential: ModelProviderCredential) -> None:
        self.credentials.pop(credential.id, None)
        await self.session.delete(credential)

    async def get_injection_pattern(self, pattern_id: UUID) -> InjectionDefensePattern | None:
        return self.patterns.get(pattern_id)

    async def list_injection_patterns(
        self,
        *,
        layer: str | None = None,
        workspace_id: UUID | None = None,
    ) -> list[InjectionDefensePattern]:
        return [
            pattern
            for pattern in self.patterns.values()
            if (layer is None or pattern.layer == layer)
            and (workspace_id is None or pattern.workspace_id in {None, workspace_id})
        ]

    async def delete_injection_pattern(self, pattern: InjectionDefensePattern) -> None:
        self.patterns.pop(pattern.id, None)
        await self.session.delete(pattern)


def _entry(
    *,
    model_id: str = "gpt-4o",
    tier: str = "tier1",
    context_window: int = 128000,
    status: str = "approved",
    expires_at: datetime | None = None,
) -> ModelCatalogEntry:
    return ModelCatalogEntry(
        id=uuid4(),
        provider="openai",
        model_id=model_id,
        display_name=model_id,
        approved_use_cases=["general"],
        prohibited_use_cases=[],
        context_window=context_window,
        input_cost_per_1k_tokens=Decimal("0.005"),
        output_cost_per_1k_tokens=Decimal("0.015"),
        quality_tier=tier,
        approved_by=uuid4(),
        approved_at=datetime.now(UTC) - timedelta(days=10),
        approval_expires_at=expires_at or datetime.now(UTC) + timedelta(days=365),
        status=status,
    )


def _catalog_create() -> CatalogEntryCreate:
    return CatalogEntryCreate(
        provider="openai",
        model_id="gpt-4o",
        context_window=128000,
        input_cost_per_1k_tokens=Decimal("0.005"),
        output_cost_per_1k_tokens=Decimal("0.015"),
        quality_tier="tier1",
        approval_expires_at=datetime.now(UTC) + timedelta(days=365),
    )


@pytest.mark.asyncio
async def test_catalog_service_create_duplicate_transitions_and_reapprove() -> None:
    repo = RepositoryStub()
    service = CatalogService(repo)  # type: ignore[arg-type]
    actor_id = uuid4()

    created = await service.create_entry(_catalog_create(), approved_by=actor_id)
    with pytest.raises(ValidationError):
        await service.create_entry(_catalog_create(), approved_by=actor_id)
    blocked = await service.block_entry(
        created.id,
        BlockRequest(justification="risk"),
        changed_by=actor_id,
    )
    reapproved = await service.reapprove_entry(
        created.id,
        ReapproveRequest(
            approval_expires_at=datetime.now(UTC) + timedelta(days=30),
            justification="reviewed",
        ),
        changed_by=actor_id,
    )

    assert blocked.status == "blocked"
    assert reapproved.status == "approved"
    assert repo.session.flush_count >= 3


@pytest.mark.asyncio
async def test_catalog_service_list_get_update_deprecate_and_missing_paths() -> None:
    repo = RepositoryStub()
    entry = _entry()
    repo.entries[entry.id] = entry
    service = CatalogService(repo)  # type: ignore[arg-type]
    actor_id = uuid4()

    listed = await service.list_entries(provider="openai", status="approved")
    loaded = await service.get_entry(entry.id)
    updated = await service.update_entry(
        entry.id,
        CatalogEntryPatch(display_name="Primary GPT-4o", approved_use_cases=["analysis"]),
        changed_by=actor_id,
    )
    no_op = await service.update_entry(entry.id, CatalogEntryPatch(), changed_by=actor_id)
    deprecated = await service.deprecate_entry(
        entry.id,
        DeprecateRequest(justification="expiry"),
        changed_by=None,
    )
    already_deprecated = await service.deprecate_entry(
        entry.id,
        DeprecateRequest(justification="expiry"),
        changed_by=actor_id,
    )

    assert listed.total == 1
    assert loaded.id == entry.id
    assert updated.display_name == "Primary GPT-4o"
    assert no_op.id == entry.id
    assert deprecated.status == "deprecated"
    assert already_deprecated.status == "deprecated"
    with pytest.raises(NotFoundError):
        await service.get_entry(uuid4())


@pytest.mark.asyncio
async def test_fallback_policy_service_validates_chain_rules() -> None:
    repo = RepositoryStub()
    primary = _entry(context_window=1000, tier="tier1")
    fallback = _entry(model_id="gpt-4o-mini", context_window=1000, tier="tier2")
    too_small = _entry(model_id="small", context_window=500, tier="tier2")
    too_low_tier = _entry(model_id="cheap", context_window=1000, tier="tier3")
    repo.entries = {item.id: item for item in (primary, fallback, too_small, too_low_tier)}
    service = FallbackPolicyService(repo)  # type: ignore[arg-type]

    response = await service.create_policy(
        FallbackPolicyCreate(
            name="workspace default",
            scope_type="global",
            primary_model_id=primary.id,
            fallback_chain=[str(fallback.id)],
            acceptable_quality_degradation="tier_plus_one",
        )
    )
    with pytest.raises(ValidationError):
        await service.create_policy(
            FallbackPolicyCreate(
                name="cycle",
                scope_type="global",
                primary_model_id=primary.id,
                fallback_chain=[str(primary.id)],
            )
        )
    with pytest.raises(ValidationError):
        await service.create_policy(
            FallbackPolicyCreate(
                name="small",
                scope_type="global",
                primary_model_id=primary.id,
                fallback_chain=[str(too_small.id)],
            )
        )
    with pytest.raises(ValidationError):
        await service.create_policy(
            FallbackPolicyCreate(
                name="tier",
                scope_type="global",
                primary_model_id=primary.id,
                fallback_chain=[str(too_low_tier.id)],
                acceptable_quality_degradation="tier_equal",
            )
        )

    assert response.fallback_chain == [str(fallback.id)]
    assert (await service.list_policies()).total == 1
    assert await service.resolve_policy_for_scope(
        workspace_id=uuid4(),
        agent_id=None,
        primary_model_id=primary.id,
    )
    await service.delete_policy(response.id)
    assert repo.session.deleted


@pytest.mark.asyncio
async def test_fallback_policy_service_update_resolution_and_lookup_edges() -> None:
    repo = RepositoryStub()
    primary = _entry(context_window=1000, tier="tier1")
    fallback = _entry(model_id="gpt-4o-mini", context_window=2000, tier="tier2")
    blocked_primary = _entry(model_id="blocked-primary", status="blocked")
    blocked_fallback = _entry(model_id="blocked-fallback", status="blocked")
    repo.entries = {
        item.id: item for item in (primary, fallback, blocked_primary, blocked_fallback)
    }
    service = FallbackPolicyService(repo)  # type: ignore[arg-type]

    created = await service.create_policy(
        FallbackPolicyCreate(
            name="global",
            scope_type="global",
            primary_model_id=primary.id,
            fallback_chain=["openai:gpt-4o-mini"],
        )
    )
    updated = await service.update_policy(
        created.id,
        FallbackPolicyPatch(
            name="updated",
            fallback_chain=[str(fallback.id)],
            retry_count=4,
            recovery_window_seconds=900,
        ),
    )
    workspace_id = uuid4()
    agent_id = uuid4()
    workspace_policy = ModelFallbackPolicy(
        id=uuid4(),
        name="workspace",
        scope_type="workspace",
        scope_id=workspace_id,
        primary_model_id=primary.id,
        fallback_chain=[str(fallback.id)],
        retry_count=3,
        backoff_strategy="exponential",
        acceptable_quality_degradation="tier_plus_one",
        recovery_window_seconds=300,
    )
    agent_policy = ModelFallbackPolicy(
        id=uuid4(),
        name="agent",
        scope_type="agent",
        scope_id=agent_id,
        primary_model_id=primary.id,
        fallback_chain=[str(fallback.id)],
        retry_count=3,
        backoff_strategy="exponential",
        acceptable_quality_degradation="tier_plus_one",
        recovery_window_seconds=300,
    )
    repo.policies[workspace_policy.id] = workspace_policy
    repo.policies[agent_policy.id] = agent_policy

    assert updated.name == "updated"
    assert updated.retry_count == 4
    assert (
        await service.resolve_policy_for_scope(
            workspace_id=workspace_id,
            agent_id=agent_id,
            primary_model_id=primary.id,
        )
    ).id == agent_policy.id
    repo.policies.pop(agent_policy.id)
    assert (
        await service.resolve_policy_for_scope(
            workspace_id=workspace_id,
            agent_id=agent_id,
            primary_model_id=primary.id,
        )
    ).id == workspace_policy.id
    repo.policies.pop(workspace_policy.id)
    assert (
        await service.resolve_policy_for_scope(
            workspace_id=workspace_id,
            agent_id=agent_id,
            primary_model_id=primary.id,
        )
    ).id == created.id
    repo.policies.clear()
    assert await service.resolve_policy_for_scope(
        workspace_id=workspace_id,
        agent_id=agent_id,
        primary_model_id=primary.id,
    ) is None

    with pytest.raises(ValidationError):
        await service.create_policy(
            FallbackPolicyCreate(
                name="bad-item",
                scope_type="global",
                primary_model_id=primary.id,
                fallback_chain=["not-a-provider-model"],
            )
        )
    with pytest.raises(NotFoundError):
        await service.create_policy(
            FallbackPolicyCreate(
                name="missing-provider",
                scope_type="global",
                primary_model_id=primary.id,
                fallback_chain=["missing:model"],
            )
        )
    with pytest.raises(ValidationError):
        await service.create_policy(
            FallbackPolicyCreate(
                name="blocked-primary",
                scope_type="global",
                primary_model_id=blocked_primary.id,
                fallback_chain=[str(fallback.id)],
            )
        )
    with pytest.raises(ValidationError):
        await service.create_policy(
            FallbackPolicyCreate(
                name="blocked-fallback",
                scope_type="global",
                primary_model_id=primary.id,
                fallback_chain=[str(blocked_fallback.id)],
            )
        )
    with pytest.raises(NotFoundError):
        await service.create_policy(
            FallbackPolicyCreate(
                name="missing-primary",
                scope_type="global",
                primary_model_id=uuid4(),
                fallback_chain=[str(fallback.id)],
            )
        )
    with pytest.raises(NotFoundError):
        await service.update_policy(uuid4(), FallbackPolicyPatch(name="missing"))


@pytest.mark.asyncio
async def test_model_card_service_material_change_flags_trust() -> None:
    repo = RepositoryStub()
    entry = _entry()
    repo.entries[entry.id] = entry
    trust = SimpleNamespace(calls=[])

    async def _flag(catalog_entry_id: UUID) -> None:
        trust.calls.append(catalog_entry_id)

    trust.flag_affected_certifications_for_rereview = _flag
    service = ModelCardService(repo, trust_service=trust)  # type: ignore[arg-type]

    first = await service.upsert_card(
        entry.id,
        ModelCardFields(safety_evaluations={"risk": "low"}, bias_assessments={"bias": "low"}),
    )
    second = await service.upsert_card(
        entry.id,
        ModelCardFields(safety_evaluations={"risk": "medium"}, bias_assessments={"bias": "low"}),
    )

    assert first.revision == 1
    assert second.revision == 2
    assert second.material is True
    assert trust.calls == [entry.id]
    assert await service.get_card_history(entry.id)


@pytest.mark.asyncio
async def test_model_card_service_get_card_and_missing_paths() -> None:
    repo = RepositoryStub()
    entry = _entry()
    repo.entries[entry.id] = entry
    service = ModelCardService(repo)  # type: ignore[arg-type]

    with pytest.raises(NotFoundError):
        await service.upsert_card(uuid4(), ModelCardFields())
    with pytest.raises(NotFoundError):
        await service.get_card(entry.id)

    created = await service.upsert_card(entry.id, ModelCardFields(capabilities="general"))
    loaded = await service.get_card(entry.id)

    assert created.revision == 1
    assert loaded.id == created.id


class SecretReaderStub:
    def __init__(self, value: str = "secret") -> None:
        self.value = value

    async def get_current(self, secret_name: str) -> str:
        del secret_name
        return self.value


class RotationServiceStub:
    async def create_schedule(self, **kwargs: object) -> SimpleNamespace:
        del kwargs
        return SimpleNamespace(id=uuid4())

    async def trigger(self, schedule_id: UUID, **kwargs: object) -> SimpleNamespace:
        del kwargs
        return SimpleNamespace(id=schedule_id, rotation_state="overlap", overlap_ends_at=None)


@pytest.mark.asyncio
async def test_credential_service_registers_and_delegates_rotation() -> None:
    repo = RepositoryStub()
    workspace_id = uuid4()
    service = CredentialService(
        repo,  # type: ignore[arg-type]
        secret_reader=SecretReaderStub(),
        rotation_service=RotationServiceStub(),  # type: ignore[arg-type]
    )
    credential = await service.register_credential(
        CredentialCreate(workspace_id=workspace_id, provider="openai", vault_ref="vault://openai")
    )

    with pytest.raises(ValidationError):
        await service.register_credential(
            CredentialCreate(
                workspace_id=workspace_id,
                provider="openai",
                vault_ref="vault://openai",
            )
        )
    with pytest.raises(AuthorizationError):
        await service.trigger_rotation(
            credential.id,
            CredentialRotateRequest(
                overlap_window_hours=0,
                emergency=True,
                approved_by=workspace_id,
            ),
            requester_id=workspace_id,
        )
    rotated = await service.trigger_rotation(
        credential.id,
        CredentialRotateRequest(overlap_window_hours=24),
        requester_id=workspace_id,
    )

    assert rotated.rotation_state == "overlap"
    assert repo.credentials[credential.id].rotation_schedule_id is not None
    assert (await service.list_credentials(workspace_id=workspace_id)).total == 1


@pytest.mark.asyncio
async def test_credential_service_rejects_empty_vault_ref() -> None:
    service = CredentialService(
        RepositoryStub(),  # type: ignore[arg-type]
        secret_reader=SecretReaderStub(value=""),
    )

    with pytest.raises(ValidationError):
        await service.register_credential(
            CredentialCreate(workspace_id=uuid4(), provider="openai", vault_ref="empty")
        )


@pytest.mark.asyncio
async def test_credential_service_lookup_update_delete_and_unavailable_paths() -> None:
    repo = RepositoryStub()
    workspace_id = uuid4()
    service = CredentialService(
        repo,  # type: ignore[arg-type]
        secret_reader=SecretReaderStub(),
    )
    credential = await service.register_credential(
        CredentialCreate(workspace_id=workspace_id, provider="openai", vault_ref="vault://old")
    )

    loaded = await service.get_by_workspace_provider(workspace_id, "openai")
    updated = await service.update_vault_ref(credential.id, "vault://new")

    assert loaded.id == credential.id
    assert updated.vault_ref == "vault://new"
    with pytest.raises(NotFoundError):
        await service.get_by_workspace_provider(workspace_id, "anthropic")
    with pytest.raises(ValidationError):
        await service.trigger_rotation(
            credential.id,
            CredentialRotateRequest(overlap_window_hours=24),
            requester_id=workspace_id,
        )
    await service.delete_credential(credential.id)
    assert credential.id not in repo.credentials
    with pytest.raises(NotFoundError):
        await service.update_vault_ref(uuid4(), "vault://missing")


@pytest.mark.asyncio
async def test_credential_service_accepts_unverified_vault_ref_when_reader_absent() -> None:
    repo = RepositoryStub()
    service = CredentialService(repo)  # type: ignore[arg-type]
    workspace_id = uuid4()

    credential = await service.register_credential(
        CredentialCreate(workspace_id=workspace_id, provider="google", vault_ref="vault://google")
    )

    assert credential.provider == "google"
    assert repo.credentials[credential.id].vault_ref == "vault://google"


class FailingSecretReaderStub:
    async def get_current(self, secret_name: str) -> str:
        del secret_name
        raise RuntimeError("vault unavailable")


@pytest.mark.asyncio
async def test_credential_service_wraps_vault_resolution_errors() -> None:
    service = CredentialService(
        RepositoryStub(),  # type: ignore[arg-type]
        secret_reader=FailingSecretReaderStub(),
    )

    with pytest.raises(ValidationError):
        await service.register_credential(
            CredentialCreate(workspace_id=uuid4(), provider="openai", vault_ref="vault://down")
        )


@pytest.mark.asyncio
async def test_injection_defense_service_crud_and_seeded_delete_guard() -> None:
    repo = RepositoryStub()
    service = InjectionDefenseService(repo)  # type: ignore[arg-type]
    pattern = await service.create_pattern(
        InjectionPatternCreate(
            pattern_name="ignore",
            pattern_regex="ignore previous",
            severity="high",
            layer="input_sanitizer",
            action="reject",
        )
    )
    finding = service.record_finding(
        layer="input_sanitizer",
        pattern_name="ignore",
        severity="high",
        action_taken="reject",
        workspace_id=uuid4(),
    )
    repo.patterns[pattern.id].seeded = True

    with pytest.raises(AuthorizationError):
        await service.delete_pattern(pattern.id)
    assert (await service.list_patterns(layer="input_sanitizer")).total == 1
    assert service.list_findings(layer="input_sanitizer")[0].pattern_name == finding.pattern_name


@pytest.mark.asyncio
async def test_injection_defense_service_update_delete_findings_and_missing_paths() -> None:
    repo = RepositoryStub()
    service = InjectionDefenseService(repo)  # type: ignore[arg-type]
    workspace_id = uuid4()
    pattern = await service.create_pattern(
        InjectionPatternCreate(
            pattern_name="leak",
            pattern_regex="secret",
            severity="medium",
            layer="output_validator",
            action="redact",
            workspace_id=workspace_id,
        )
    )
    updated = await service.update_pattern(
        pattern.id,
        InjectionPatternPatch(severity="high", action="block"),
    )
    service.record_finding(
        layer="output_validator",
        pattern_name="leak",
        severity="high",
        action_taken="block",
        workspace_id=workspace_id,
        agent_id=uuid4(),
    )

    assert updated.severity == "high"
    assert service.list_findings(workspace_id=workspace_id)[0].workspace_id == workspace_id
    await service.delete_pattern(pattern.id)
    assert pattern.id not in repo.patterns
    with pytest.raises(NotFoundError):
        await service.update_pattern(uuid4(), InjectionPatternPatch(action="redact"))


@pytest.mark.asyncio
async def test_auto_deprecation_scanner_deprecates_and_records_gaps() -> None:
    repo = RepositoryStub()
    expired = _entry(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    missing_card = _entry(model_id="new-approved")
    repo.entries = {expired.id: expired, missing_card.id: missing_card}
    compliance = SimpleNamespace(calls=[])

    async def _on_security_event(**kwargs: object) -> list[object]:
        compliance.calls.append(kwargs)
        return []

    compliance.on_security_event = _on_security_event

    result = await run_auto_deprecation_scan(
        repository=repo,  # type: ignore[arg-type]
        compliance_service=compliance,
    )

    assert result == {"deprecated": 1, "compliance_gaps": 1}
    assert expired.status == "deprecated"
    assert compliance.calls[0]["evidence_type"] == "model_card_missing"


@pytest.mark.asyncio
async def test_catalog_and_auto_deprecation_write_audit_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit_calls: list[tuple[object, UUID, str, dict[str, object]]] = []

    async def _record_audit(
        audit_chain: object,
        audit_event_id: UUID,
        source: str,
        canonical_payload: dict[str, object],
    ) -> None:
        audit_calls.append((audit_chain, audit_event_id, source, canonical_payload))

    monkeypatch.setattr(
        "platform.model_catalog.services.catalog_service.audit_chain_hook",
        _record_audit,
    )
    monkeypatch.setattr(
        "platform.model_catalog.workers.auto_deprecation_scanner.audit_chain_hook",
        _record_audit,
    )
    repo = RepositoryStub()
    entry = _entry(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    repo.entries[entry.id] = entry
    audit_chain = object()

    service = CatalogService(
        repo,  # type: ignore[arg-type]
        audit_chain=audit_chain,  # type: ignore[arg-type]
    )
    await service.block_entry(entry.id, BlockRequest(justification="risk"), changed_by=uuid4())
    entry.status = "approved"
    await run_auto_deprecation_scan(
        repository=repo,  # type: ignore[arg-type]
        audit_chain=audit_chain,  # type: ignore[arg-type]
    )

    assert [call[3]["event"] for call in audit_calls] == [
        "model.catalog.updated",
        "model.deprecated",
    ]
