from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.common.clients.model_provider_http import ProviderResponse
from platform.common.clients.model_router import ModelRouter
from platform.common.llm.exceptions import RateLimitError
from platform.model_catalog.models import (
    ModelCatalogEntry,
    ModelFallbackPolicy,
    ModelProviderCredential,
)
from typing import Any
from uuid import UUID, uuid4

import pytest


class RepositoryStub:
    def __init__(self) -> None:
        self.entries_by_binding: dict[str, ModelCatalogEntry] = {}
        self.entries_by_id: dict[UUID, ModelCatalogEntry] = {}
        self.policy: ModelFallbackPolicy | None = None
        self.credentials: dict[tuple[UUID, str], ModelProviderCredential] = {}

    def add_entry(self, entry: ModelCatalogEntry) -> None:
        self.entries_by_binding[f"{entry.provider}:{entry.model_id}"] = entry
        self.entries_by_id[entry.id] = entry

    async def get_entry_by_provider_model(
        self,
        provider: str,
        model_id: str,
    ) -> ModelCatalogEntry | None:
        return self.entries_by_binding.get(f"{provider}:{model_id}")

    async def get_entry(self, entry_id: UUID) -> ModelCatalogEntry | None:
        return self.entries_by_id.get(entry_id)

    async def get_fallback_policy_for_scope(
        self,
        *,
        scope_type: str,
        scope_id: UUID | None,
        primary_model_id: UUID,
    ) -> ModelFallbackPolicy | None:
        del scope_type, scope_id, primary_model_id
        return self.policy

    async def get_credential_by_workspace_provider(
        self,
        workspace_id: UUID,
        provider: str,
    ) -> ModelProviderCredential | None:
        return self.credentials.get((workspace_id, provider))

    async def list_injection_patterns_for_layer(
        self,
        layer: str,
        *,
        workspace_id: UUID | None = None,
    ) -> list[object]:
        del layer, workspace_id
        return []


class SecretProviderStub:
    async def get_current(self, secret_name: str) -> str:
        return f"key:{secret_name}"


class ProviderStub:
    def __init__(self, results: list[ProviderResponse | Exception]) -> None:
        self.results = results
        self.models_called: list[str] = []

    async def __call__(self, **kwargs: Any) -> ProviderResponse:
        self.models_called.append(str(kwargs["model_id"]))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _entry(provider: str, model_id: str, *, tier: str) -> ModelCatalogEntry:
    return ModelCatalogEntry(
        id=uuid4(),
        provider=provider,
        model_id=model_id,
        display_name=model_id,
        approved_use_cases=["general"],
        prohibited_use_cases=[],
        context_window=128000,
        input_cost_per_1k_tokens=Decimal("0.005"),
        output_cost_per_1k_tokens=Decimal("0.015"),
        quality_tier=tier,
        approved_by=uuid4(),
        approved_at=datetime.now(UTC),
        approval_expires_at=datetime.now(UTC) + timedelta(days=365),
        status="approved",
    )


def _provider_payload(content: str) -> ProviderResponse:
    return ProviderResponse(
        status_code=200,
        payload={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )


@pytest.mark.asyncio
async def test_model_router_walks_fallback_chain_on_synthetic_rate_limit() -> None:
    workspace_id = uuid4()
    repo = RepositoryStub()
    primary = _entry("openai", "gpt-4o", tier="tier1")
    tier2 = _entry("anthropic", "claude-sonnet", tier="tier2")
    tier3 = _entry("mistral", "large", tier="tier3")
    for entry in (primary, tier2, tier3):
        repo.add_entry(entry)
        repo.credentials[(workspace_id, entry.provider)] = ModelProviderCredential(
            id=uuid4(),
            workspace_id=workspace_id,
            provider=entry.provider,
            vault_ref=f"vault://{entry.provider}",
        )
    repo.policy = ModelFallbackPolicy(
        id=uuid4(),
        name="global",
        scope_type="global",
        scope_id=None,
        primary_model_id=primary.id,
        fallback_chain=[str(tier2.id), str(tier3.id)],
        retry_count=1,
        backoff_strategy="fixed",
        acceptable_quality_degradation="tier_plus_two",
        recovery_window_seconds=300,
    )
    provider = ProviderStub(
        [
            RateLimitError("primary synthetic 429"),
            RateLimitError("tier2 synthetic 429"),
            _provider_payload("tier3 response"),
        ]
    )
    router = ModelRouter(
        repository=repo,  # type: ignore[arg-type]
        secret_provider=SecretProviderStub(),
        provider_call=provider,
    )

    result = await router.complete(
        workspace_id=workspace_id,
        step_binding="openai:gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
    )

    assert result.content == "tier3 response"
    assert result.model_used == "mistral:large"
    assert result.fallback_taken is not None
    assert result.fallback_taken.failure_reason == "provider_rate_limited"
    assert result.fallback_taken.fallback_chain_index == 1
    assert provider.models_called == ["gpt-4o", "claude-sonnet", "large"]
