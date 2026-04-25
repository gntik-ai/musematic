from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.common.clients import model_provider_http
from platform.common.clients.injection_defense import (
    input_sanitizer,
    output_validator,
    system_prompt_hardener,
)
from platform.common.clients.model_provider_http import (
    ProviderAuthError,
    ProviderOutage,
    ProviderTimeout,
    RateLimitedError,
)
from platform.common.clients.model_router import __doc__ as model_router_doc
from platform.model_catalog import events
from platform.model_catalog.exceptions import (
    ModelBindingError,
    ModelCatalogNotFoundError,
    ProviderCallError,
)
from platform.model_catalog.models import (
    InjectionDefensePattern,
    ModelCard,
    ModelCatalogEntry,
    ModelFallbackPolicy,
    ModelProviderCredential,
)
from platform.model_catalog.repository import ModelCatalogRepository
from platform.model_catalog.schemas import CatalogEntryResponse, FallbackPolicyResponse
from types import SimpleNamespace
from typing import Any, ClassVar
from uuid import uuid4

import httpx
import pytest


class ResultStub:
    def __init__(self, *, scalar: object | None = None, items: list[object] | None = None) -> None:
        self.scalar = scalar
        self.items = items or []

    def scalar_one_or_none(self) -> object | None:
        return self.scalar

    def scalars(self) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: self.items, first=lambda: self.items[0])


class SessionStub:
    def __init__(self, execute_results: list[ResultStub] | None = None) -> None:
        self.execute_results = execute_results or []
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.flush_count = 0
        self.get_calls: list[tuple[type[object], object]] = []
        self.get_result: object | None = None
        self.statements: list[object] = []

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flush_count += 1

    async def delete(self, item: object) -> None:
        self.deleted.append(item)

    async def get(self, model: type[object], key: object) -> object | None:
        self.get_calls.append((model, key))
        return self.get_result

    async def execute(self, statement: object) -> ResultStub:
        self.statements.append(statement)
        return self.execute_results.pop(0)


class FakeProducer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def publish(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def _entry() -> ModelCatalogEntry:
    return ModelCatalogEntry(
        id=uuid4(),
        provider="openai",
        model_id="gpt-4o",
        display_name="GPT-4o",
        approved_use_cases=["general"],
        prohibited_use_cases=[],
        context_window=128000,
        input_cost_per_1k_tokens=Decimal("0.005"),
        output_cost_per_1k_tokens=Decimal("0.015"),
        quality_tier="tier1",
        approved_by=uuid4(),
        approved_at=datetime.now(UTC),
        approval_expires_at=datetime.now(UTC) + timedelta(days=365),
        status="approved",
    )


@pytest.mark.asyncio
async def test_repository_read_helpers_are_side_effect_free() -> None:
    entry = _entry()
    card = ModelCard(id=uuid4(), catalog_entry_id=entry.id, revision=1)
    policy = ModelFallbackPolicy(
        id=uuid4(),
        name="default",
        scope_type="global",
        scope_id=None,
        primary_model_id=entry.id,
        fallback_chain=["anthropic:claude-sonnet-4-6"],
        retry_count=1,
        backoff_strategy="fixed",
        acceptable_quality_degradation="tier_plus_one",
        recovery_window_seconds=300,
    )
    credential = ModelProviderCredential(
        id=uuid4(),
        workspace_id=uuid4(),
        provider="openai",
        vault_ref="vault://model/openai",
    )
    pattern = InjectionDefensePattern(
        id=uuid4(),
        pattern_name="ignore_previous",
        pattern_regex="ignore previous instructions",
        severity="high",
        layer="input_sanitizer",
        action="reject",
        seeded=True,
    )
    session = SessionStub(
        execute_results=[
            ResultStub(scalar=entry),
            ResultStub(items=[entry]),
            ResultStub(scalar=card),
            ResultStub(items=[policy]),
            ResultStub(scalar=credential),
            ResultStub(items=[pattern]),
        ]
    )
    session.get_result = entry
    repo = ModelCatalogRepository(session)  # type: ignore[arg-type]

    assert await repo.get_entry(entry.id) is entry
    assert await repo.get_entry_by_provider_model("openai", "gpt-4o") is entry
    assert await repo.list_entries(provider="openai", status="approved") == [entry]
    assert await repo.get_card_by_entry_id(entry.id) is card
    assert (
        await repo.get_fallback_policy_for_scope(
            scope_type="global",
            scope_id=None,
            primary_model_id=entry.id,
        )
        is policy
    )
    assert (
        await repo.get_credential_by_workspace_provider(credential.workspace_id, "openai")
        is credential
    )
    assert await repo.list_injection_patterns_for_layer("input_sanitizer") == [pattern]

    assert session.added == []
    assert session.flush_count == 0
    assert session.get_calls == [(ModelCatalogEntry, entry.id)]


@pytest.mark.asyncio
async def test_repository_add_flushes_and_returns_item() -> None:
    session = SessionStub()
    repo = ModelCatalogRepository(session)  # type: ignore[arg-type]
    entry = _entry()

    assert await repo.add(entry) is entry

    assert session.added == [entry]
    assert session.flush_count == 1


@pytest.mark.asyncio
async def test_repository_crud_and_list_filters_cover_all_entities() -> None:
    entry = _entry()
    card = ModelCard(id=uuid4(), catalog_entry_id=entry.id, revision=2)
    policy = ModelFallbackPolicy(
        id=uuid4(),
        name="agent",
        scope_type="agent",
        scope_id=uuid4(),
        primary_model_id=entry.id,
        fallback_chain=["openai:gpt-4o-mini"],
        retry_count=2,
        backoff_strategy="linear",
        acceptable_quality_degradation="tier_plus_one",
        recovery_window_seconds=600,
    )
    credential = ModelProviderCredential(
        id=uuid4(),
        workspace_id=uuid4(),
        provider="anthropic",
        vault_ref="vault://model/anthropic",
    )
    pattern = InjectionDefensePattern(
        id=uuid4(),
        pattern_name="role_reversal",
        pattern_regex="you are now",
        severity="medium",
        layer="output_validator",
        action="redact",
        workspace_id=uuid4(),
        seeded=False,
    )
    session = SessionStub(
        execute_results=[
            ResultStub(items=[entry]),
            ResultStub(items=[card]),
            ResultStub(items=[entry]),
            ResultStub(items=[entry]),
            ResultStub(items=[policy]),
            ResultStub(items=[credential]),
            ResultStub(items=[pattern]),
            ResultStub(items=[pattern]),
        ]
    )
    repo = ModelCatalogRepository(session)  # type: ignore[arg-type]

    assert await repo.list_entries() == [entry]
    assert await repo.list_card_history(entry.id) == [card]
    assert await repo.list_entries_missing_cards() == [entry]
    assert await repo.list_expired_approved_entries(now=datetime.now(UTC)) == [entry]
    assert (
        await repo.list_fallback_policies(
            primary_model_id=entry.id,
            scope_type="agent",
        )
        == [policy]
    )
    assert (
        await repo.list_credentials(
            workspace_id=credential.workspace_id,
            provider="anthropic",
        )
        == [credential]
    )
    assert await repo.list_injection_patterns_for_layer(
        "output_validator",
        workspace_id=pattern.workspace_id,
    ) == [pattern]
    assert await repo.list_injection_patterns(
        layer="output_validator",
        workspace_id=pattern.workspace_id,
    ) == [pattern]

    session.get_result = policy
    assert await repo.get_fallback_policy(policy.id) is policy
    session.get_result = credential
    assert await repo.get_credential(credential.id) is credential
    session.get_result = pattern
    assert await repo.get_injection_pattern(pattern.id) is pattern

    await repo.delete_fallback_policy(policy)
    await repo.delete_credential(credential)
    await repo.delete_injection_pattern(pattern)

    assert session.deleted == [policy, credential, pattern]
    assert session.flush_count == 3
    assert await repo.delete_injection_findings_before(datetime.now(UTC)) == 0


def test_event_registry_schemas_and_payload_models() -> None:
    events.register_model_catalog_event_types()

    for event_type in events.MODEL_CATALOG_EVENT_SCHEMAS:
        assert events.event_registry.is_registered(event_type)

    assert events.ModelCatalogUpdatedPayload(
        catalog_entry_id=uuid4(),
        provider="openai",
        model_id="gpt-4o",
        status="approved",
    ).status == "approved"


@pytest.mark.asyncio
async def test_event_publish_helpers_noop_and_emit_payload() -> None:
    correlation_id = uuid4()
    workspace_id = uuid4()
    catalog_entry_id = uuid4()
    payload = events.ModelCatalogUpdatedPayload(
        catalog_entry_id=catalog_entry_id,
        provider="openai",
        model_id="gpt-4o",
        status="approved",
    )

    await events.publish_model_catalog_updated(payload, correlation_id, None)
    producer = FakeProducer()
    await events.publish_model_catalog_updated(
        payload,
        correlation_id,
        producer,  # type: ignore[arg-type]
        workspace_id=workspace_id,
    )

    assert producer.calls[0]["topic"] == "model.catalog.events"
    assert producer.calls[0]["event_type"] == "model.catalog.updated"
    assert producer.calls[0]["key"] == str(catalog_entry_id)
    assert producer.calls[0]["payload"] == {
        "catalog_entry_id": str(catalog_entry_id),
        "provider": "openai",
        "model_id": "gpt-4o",
        "status": "approved",
        "changed_by": None,
    }


class DummyAsyncClient:
    response: httpx.Response | None = None
    exception: Exception | None = None
    instances: ClassVar[list[DummyAsyncClient]] = []

    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout
        self.calls: list[dict[str, Any]] = []
        self.instances.append(self)

    async def __aenter__(self) -> DummyAsyncClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(
        self,
        url: str,
        *,
        json: dict[str, object],
        headers: dict[str, str],
    ) -> httpx.Response:
        self.calls.append({"url": url, "json": json, "headers": headers})
        if self.exception is not None:
            raise self.exception
        assert self.response is not None
        return self.response


@pytest.fixture(autouse=True)
def _reset_dummy_client() -> None:
    DummyAsyncClient.response = None
    DummyAsyncClient.exception = None
    DummyAsyncClient.instances = []


@pytest.mark.asyncio
async def test_model_provider_http_call_builds_openai_compatible_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    DummyAsyncClient.response = httpx.Response(
        200,
        json={"choices": []},
        request=httpx.Request("POST", "https://provider.example/v1/chat/completions"),
    )
    monkeypatch.setattr(model_provider_http.httpx, "AsyncClient", DummyAsyncClient)

    response = await model_provider_http.call(
        base_url="https://provider.example/v1/chat/completions",
        api_key="secret",
        model_id="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
        response_format={"type": "json_object"},
        timeout=1.5,
    )

    assert response.payload == {"choices": []}
    assert response.status_code == 200
    client = DummyAsyncClient.instances[0]
    assert client.timeout == 1.5
    assert client.calls[0]["headers"] == {"Authorization": "Bearer secret"}
    assert client.calls[0]["json"] == {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "hello"}],
        "response_format": {"type": "json_object"},
    }


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (429, RateLimitedError),
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (500, ProviderOutage),
    ],
)
@pytest.mark.asyncio
async def test_model_provider_http_maps_provider_status_errors(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected_error: type[Exception],
) -> None:
    DummyAsyncClient.response = httpx.Response(
        status_code,
        text="provider error",
        request=httpx.Request("POST", "https://provider.example/v1/chat/completions"),
    )
    monkeypatch.setattr(model_provider_http.httpx, "AsyncClient", DummyAsyncClient)

    with pytest.raises(expected_error):
        await model_provider_http.call(
            base_url="https://provider.example/v1/chat/completions",
            api_key="secret",
            model_id="gpt-4o",
            messages=[],
            response_format=None,
            timeout=1.0,
        )


@pytest.mark.asyncio
async def test_model_provider_http_maps_transport_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_provider_http.httpx, "AsyncClient", DummyAsyncClient)
    DummyAsyncClient.exception = httpx.TimeoutException("timed out")

    with pytest.raises(ProviderTimeout):
        await model_provider_http.call(
            base_url="https://provider.example/v1/chat/completions",
            api_key="secret",
            model_id="gpt-4o",
            messages=[],
            response_format=None,
            timeout=1.0,
        )

    DummyAsyncClient.exception = httpx.ConnectError("down")
    with pytest.raises(ProviderOutage):
        await model_provider_http.call(
            base_url="https://provider.example/v1/chat/completions",
            api_key="secret",
            model_id="gpt-4o",
            messages=[],
            response_format=None,
            timeout=1.0,
        )


def test_foundation_schemas_exceptions_and_scaffold_modules() -> None:
    entry = _entry()
    catalog_response = CatalogEntryResponse(
        id=entry.id,
        provider=entry.provider,
        model_id=entry.model_id,
        display_name=entry.display_name,
        context_window=entry.context_window,
        input_cost_per_1k_tokens=entry.input_cost_per_1k_tokens,
        output_cost_per_1k_tokens=entry.output_cost_per_1k_tokens,
        quality_tier=entry.quality_tier,
        status=entry.status,
        approval_expires_at=entry.approval_expires_at,
    )
    fallback_response = FallbackPolicyResponse(
        id=uuid4(),
        name="default",
        scope_type="global",
        scope_id=None,
        primary_model_id=entry.id,
    )

    assert catalog_response.model_id == "gpt-4o"
    assert fallback_response.fallback_chain == []
    assert ModelCatalogNotFoundError("missing", "not found").status_code == 404
    assert ModelBindingError("invalid", "blocked").status_code == 422
    assert ProviderCallError("failed", "provider down").status_code == 502
    assert input_sanitizer.__doc__
    assert system_prompt_hardener.__doc__
    assert output_validator.__doc__
    assert model_router_doc
