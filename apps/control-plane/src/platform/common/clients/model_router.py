"""Provider-agnostic model router with catalogue validation and fallback dispatch."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from importlib import import_module
from platform.billing.quotas.http import raise_for_quota_result
from platform.common.clients import model_provider_http
from platform.common.clients.injection_defense.input_sanitizer import sanitize_messages
from platform.common.clients.injection_defense.output_validator import validate_output
from platform.common.clients.injection_defense.system_prompt_hardener import harden_messages
from platform.common.clients.model_provider_http import (
    ProviderOutage,
    ProviderResponse,
    ProviderTimeout,
    RateLimitedError,
)
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from platform.common.events.producer import EventProducer
from platform.model_catalog.events import (
    ModelFallbackTriggeredPayload,
    publish_model_fallback_triggered,
)
from platform.model_catalog.exceptions import (
    CatalogEntryNotFoundError,
    CredentialNotConfiguredError,
    FallbackExhaustedError,
    InvalidBindingError,
    ModelBlockedError,
    PromptInjectionBlocked,
)
from platform.model_catalog.models import ModelCatalogEntry, ModelFallbackPolicy
from platform.model_catalog.repository import ModelCatalogRepository
from typing import Any, Protocol
from uuid import UUID, uuid4

ProviderCall = Callable[..., Awaitable[ProviderResponse]]


class SecretProvider(Protocol):
    async def get_current(self, secret_name: str) -> str: ...


class RedisStickyCache(Protocol):
    async def get(self, key: str) -> bytes | str | None: ...

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None: ...


AgentResolver = Callable[[UUID], Awaitable[Any | None]]


@dataclass(frozen=True, slots=True)
class FallbackAuditRecord:
    primary_model_id: UUID
    fallback_model_id: UUID
    fallback_model_used: str
    fallback_chain_index: int
    failure_reason: str
    elapsed_latency_ms: int
    retry_attempts_on_primary: int


@dataclass(frozen=True, slots=True)
class ModelRouterResponse:
    content: str
    model_used: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    fallback_taken: FallbackAuditRecord | None
    raw_payload: dict[str, Any]


@dataclass(slots=True)
class _CacheEntry:
    value: Any
    expires_at: float


class _ModelRouterMetrics:
    def __init__(self) -> None:
        self._calls = None
        self._latency = None
        self._fallbacks = None
        self._validation_failures = None
        try:
            metrics_module = import_module("opentelemetry.metrics")
            meter = metrics_module.get_meter(__name__)
            self._calls = meter.create_counter(
                "model_router_calls_total",
                description="Model router calls by provider and fallback state.",
                unit="{call}",
            )
            self._latency = meter.create_histogram(
                "model_router_latency_seconds",
                description="Model router end-to-end latency.",
                unit="s",
            )
            self._fallbacks = meter.create_counter(
                "model_router_fallback_total",
                description="Model router fallback dispatches.",
                unit="{fallback}",
            )
            self._validation_failures = meter.create_counter(
                "model_router_validation_failures_total",
                description="Model router validation failures.",
                unit="{failure}",
            )
        except Exception:
            self._calls = None
            self._latency = None
            self._fallbacks = None
            self._validation_failures = None

    def success(self, response: ModelRouterResponse) -> None:
        attributes = {
            "model": response.model_used,
            "fallback": str(response.fallback_taken is not None).lower(),
        }
        if self._calls is not None:
            self._calls.add(1, attributes=attributes)
        if self._latency is not None:
            self._latency.record(response.latency_ms / 1000, attributes=attributes)
        if response.fallback_taken is not None and self._fallbacks is not None:
            self._fallbacks.add(1, attributes={"model": response.model_used})

    def validation_failure(self, layer: str) -> None:
        if self._validation_failures is not None:
            self._validation_failures.add(1, attributes={"layer": layer})


class ModelRouter:
    def __init__(
        self,
        *,
        repository: ModelCatalogRepository,
        secret_provider: SecretProvider,
        settings: PlatformSettings | None = None,
        redis_client: RedisStickyCache | None = None,
        event_producer: EventProducer | None = None,
        provider_call: ProviderCall = model_provider_http.call,
        agent_resolver: AgentResolver | None = None,
        quota_enforcer: Any | None = None,
        cache_ttl_seconds: int = 60,
    ) -> None:
        self.repository = repository
        self.secret_provider = secret_provider
        self.settings = settings or default_settings
        self.redis_client = redis_client
        self.event_producer = event_producer
        self.provider_call = provider_call
        self.agent_resolver = agent_resolver
        self.quota_enforcer = quota_enforcer
        self.cache_ttl_seconds = cache_ttl_seconds
        self._catalog_cache: dict[str, _CacheEntry] = {}
        self._policy_cache: dict[str, _CacheEntry] = {}
        self._metrics = _ModelRouterMetrics()

    async def complete(
        self,
        *,
        workspace_id: UUID,
        agent_id: UUID | None = None,
        step_binding: str | None = None,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
        timeout_seconds: float = 25.0,
    ) -> ModelRouterResponse:
        started = time.perf_counter()
        primary_binding = await self._resolve_binding(agent_id, step_binding)
        primary = await self._catalog_entry_for_binding(primary_binding)
        self._validate_entry(primary, primary_binding)
        if self.quota_enforcer is not None:
            quota_result = await self.quota_enforcer.check_model_tier(
                workspace_id,
                primary.model_id,
                primary.quality_tier,
            )
            raise_for_quota_result(quota_result, workspace_id=workspace_id)
        policy = await self._resolve_policy(workspace_id, agent_id, primary)
        sticky_key = self._sticky_key(workspace_id, primary.id)
        messages_to_send = await self._prepare_messages(
            workspace_id=workspace_id,
            messages=messages,
        )

        sticky_state = await self._get_sticky_state(sticky_key)
        if sticky_state == "in_fallback" and policy is not None:
            chain_response = await self._call_chain(
                workspace_id=workspace_id,
                primary=primary,
                policy=policy,
                messages=messages_to_send,
                response_format=response_format,
                timeout_seconds=timeout_seconds,
                started=started,
                failure_reason="sticky_fallback",
                primary_attempts=0,
            )
            return await self._finalize_response(workspace_id, chain_response)

        primary_attempts = max(1, policy.retry_count if policy is not None else 1)
        try:
            provider_response, _attempts = await self._call_primary(
                entry=primary,
                workspace_id=workspace_id,
                messages=messages_to_send,
                response_format=response_format,
                timeout_seconds=timeout_seconds,
                retry_count=primary_attempts,
            )
            await self._set_sticky_state(
                sticky_key,
                "use_primary",
                ttl_seconds=policy.recovery_window_seconds if policy is not None else 300,
            )
            return await self._finalize_response(
                workspace_id,
                self._router_response(primary, provider_response, started, None),
            )
        except PromptInjectionBlocked:
            self._metrics.validation_failure("prompt_injection")
            raise
        except (ProviderOutage, ProviderTimeout, RateLimitedError) as exc:
            if policy is None:
                raise
            await self._set_sticky_state(
                sticky_key,
                "in_fallback",
                ttl_seconds=policy.recovery_window_seconds,
            )
            chain_response = await self._call_chain(
                workspace_id=workspace_id,
                primary=primary,
                policy=policy,
                messages=messages_to_send,
                response_format=response_format,
                timeout_seconds=timeout_seconds,
                started=started,
                failure_reason=self._failure_reason(exc),
                primary_attempts=primary_attempts,
            )
            return await self._finalize_response(workspace_id, chain_response)

    async def _prepare_messages(
        self,
        *,
        workspace_id: UUID,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        prepared = [dict(message) for message in messages]
        if self.settings.model_catalog.injection_input_sanitizer_enabled:
            patterns = await self.repository.list_injection_patterns_for_layer(
                "input_sanitizer",
                workspace_id=workspace_id,
            )
            try:
                prepared, findings = sanitize_messages(prepared, patterns)
            except PromptInjectionBlocked:
                self._metrics.validation_failure("input_sanitizer")
                raise
            for _finding in findings:
                self._metrics.validation_failure("input_sanitizer")
        if self.settings.model_catalog.injection_system_prompt_hardener_enabled:
            prepared = harden_messages(prepared)
        return prepared

    async def _finalize_response(
        self,
        workspace_id: UUID,
        response: ModelRouterResponse,
    ) -> ModelRouterResponse:
        finalized = response
        if self.settings.model_catalog.injection_output_validator_enabled:
            patterns = await self.repository.list_injection_patterns_for_layer(
                "output_validator",
                workspace_id=workspace_id,
            )
            try:
                result = validate_output(response.content, patterns)
            except PromptInjectionBlocked:
                self._metrics.validation_failure("output_validator")
                raise
            if result.findings:
                for _finding in result.findings:
                    self._metrics.validation_failure("output_validator")
                finalized = replace(response, content=result.text)
        self._metrics.success(finalized)
        return finalized

    async def _resolve_binding(self, agent_id: UUID | None, step_binding: str | None) -> str:
        if step_binding:
            return step_binding
        if agent_id is not None and self.agent_resolver is not None:
            agent = await self.agent_resolver(agent_id)
            binding = getattr(agent, "default_model_binding", None)
            if isinstance(binding, str) and binding:
                return binding
        raise InvalidBindingError(
            "MODEL_BINDING_MISSING",
            "No model binding provided. Set step_binding or agent.default_model_binding.",
        )

    async def _catalog_entry_for_binding(self, binding: str) -> ModelCatalogEntry:
        cached = self._cache_get(self._catalog_cache, binding)
        if isinstance(cached, ModelCatalogEntry):
            return cached
        provider, model_id = self._split_binding(binding)
        entry = await self.repository.get_entry_by_provider_model(provider, model_id)
        if entry is None:
            raise CatalogEntryNotFoundError(
                "MODEL_CATALOG_ENTRY_NOT_FOUND",
                f"Model binding {binding!r} is not present in the catalogue.",
            )
        self._cache_set(self._catalog_cache, binding, entry)
        return entry

    async def _catalog_entry_for_chain_item(self, chain_item: str) -> ModelCatalogEntry:
        if ":" in chain_item:
            return await self._catalog_entry_for_binding(chain_item)
        cached = self._cache_get(self._catalog_cache, chain_item)
        if isinstance(cached, ModelCatalogEntry):
            return cached
        try:
            entry_id = UUID(chain_item)
        except ValueError as exc:
            raise CatalogEntryNotFoundError(
                "MODEL_CATALOG_ENTRY_NOT_FOUND",
                f"Fallback chain item {chain_item!r} is not a valid binding or UUID.",
            ) from exc
        entry = await self.repository.get_entry(entry_id)
        if entry is None:
            raise CatalogEntryNotFoundError(
                "MODEL_CATALOG_ENTRY_NOT_FOUND",
                f"Fallback chain item {chain_item!r} is not present in the catalogue.",
            )
        self._cache_set(self._catalog_cache, chain_item, entry)
        return entry

    async def _resolve_policy(
        self,
        workspace_id: UUID,
        agent_id: UUID | None,
        primary: ModelCatalogEntry,
    ) -> ModelFallbackPolicy | None:
        cache_key = f"{workspace_id}:{agent_id}:{primary.id}"
        cached = self._cache_get(self._policy_cache, cache_key)
        if isinstance(cached, ModelFallbackPolicy):
            return cached
        policy: ModelFallbackPolicy | None = None
        if agent_id is not None:
            policy = await self.repository.get_fallback_policy_for_scope(
                scope_type="agent",
                scope_id=agent_id,
                primary_model_id=primary.id,
            )
        if policy is None:
            policy = await self.repository.get_fallback_policy_for_scope(
                scope_type="workspace",
                scope_id=workspace_id,
                primary_model_id=primary.id,
            )
        if policy is None:
            policy = await self.repository.get_fallback_policy_for_scope(
                scope_type="global",
                scope_id=None,
                primary_model_id=primary.id,
            )
        if policy is not None:
            self._cache_set(self._policy_cache, cache_key, policy)
        return policy

    async def _call_primary(
        self,
        *,
        entry: ModelCatalogEntry,
        workspace_id: UUID,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None,
        timeout_seconds: float,
        retry_count: int,
    ) -> tuple[ProviderResponse, int]:
        attempts = max(1, retry_count)
        last_error: ProviderOutage | ProviderTimeout | RateLimitedError | None = None
        for attempt in range(1, attempts + 1):
            try:
                return (
                    await self._call_provider(
                        entry=entry,
                        workspace_id=workspace_id,
                        messages=messages,
                        response_format=response_format,
                        timeout_seconds=timeout_seconds,
                    ),
                    attempt,
                )
            except (ProviderOutage, ProviderTimeout, RateLimitedError) as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    async def _call_chain(
        self,
        *,
        workspace_id: UUID,
        primary: ModelCatalogEntry,
        policy: ModelFallbackPolicy,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None,
        timeout_seconds: float,
        started: float,
        failure_reason: str,
        primary_attempts: int,
    ) -> ModelRouterResponse:
        failures: list[dict[str, str]] = []
        for index, chain_item in enumerate(policy.fallback_chain):
            fallback = await self._catalog_entry_for_chain_item(str(chain_item))
            self._validate_entry(fallback, str(chain_item))
            try:
                response = await self._call_provider(
                    entry=fallback,
                    workspace_id=workspace_id,
                    messages=messages,
                    response_format=response_format,
                    timeout_seconds=timeout_seconds,
                )
            except (ProviderOutage, ProviderTimeout, RateLimitedError) as exc:
                failures.append(
                    {
                        "model": self._binding_for_entry(fallback),
                        "reason": self._failure_reason(exc),
                    }
                )
                continue

            audit = FallbackAuditRecord(
                primary_model_id=primary.id,
                fallback_model_id=fallback.id,
                fallback_model_used=self._binding_for_entry(fallback),
                fallback_chain_index=index,
                failure_reason=failure_reason,
                elapsed_latency_ms=self._elapsed_ms(started),
                retry_attempts_on_primary=primary_attempts,
            )
            await publish_model_fallback_triggered(
                ModelFallbackTriggeredPayload(
                    workspace_id=workspace_id,
                    primary_model_id=primary.id,
                    fallback_model_id=fallback.id,
                    reason=failure_reason,
                    triggered_at=datetime.now(UTC),
                ),
                uuid4(),
                self.event_producer,
                workspace_id=workspace_id,
            )
            return self._router_response(fallback, response, started, audit)

        raise FallbackExhaustedError(
            "MODEL_FALLBACK_EXHAUSTED",
            f"All fallback models failed: {failures}",
            {"failures": failures},
        )

    async def _call_provider(
        self,
        *,
        entry: ModelCatalogEntry,
        workspace_id: UUID,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None,
        timeout_seconds: float,
    ) -> ProviderResponse:
        credential = await self.repository.get_credential_by_workspace_provider(
            workspace_id,
            entry.provider,
        )
        if credential is None:
            raise CredentialNotConfiguredError(
                "MODEL_PROVIDER_CREDENTIAL_MISSING",
                f"No provider credential configured for {entry.provider!r}.",
            )
        api_key = await self.secret_provider.get_current(credential.vault_ref)
        return await self.provider_call(
            base_url=self._base_url_for_provider(entry.provider),
            api_key=api_key,
            model_id=entry.model_id,
            messages=messages,
            response_format=response_format,
            timeout=timeout_seconds,
        )

    def _router_response(
        self,
        entry: ModelCatalogEntry,
        provider_response: ProviderResponse,
        started: float,
        fallback: FallbackAuditRecord | None,
    ) -> ModelRouterResponse:
        payload = provider_response.payload
        usage = payload.get("usage", {})
        return ModelRouterResponse(
            content=self._extract_content(payload),
            model_used=self._binding_for_entry(entry),
            tokens_in=int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
            latency_ms=self._elapsed_ms(started),
            fallback_taken=fallback,
            raw_payload=payload,
        )

    def _base_url_for_provider(self, provider: str) -> str:
        configured = {
            "openai": self.settings.model_catalog.openai_base_url,
            "anthropic": self.settings.model_catalog.anthropic_base_url,
            "google": self.settings.model_catalog.google_base_url,
            "mistral": self.settings.model_catalog.mistral_base_url,
        }
        return configured.get(provider, self.settings.model_catalog.openai_base_url)

    def _validate_entry(self, entry: ModelCatalogEntry, binding: str) -> None:
        if entry.status == "blocked":
            raise ModelBlockedError(
                "MODEL_BLOCKED",
                f"Model binding {binding!r} is blocked in the catalogue.",
            )

    async def _get_sticky_state(self, key: str) -> str | None:
        if self.redis_client is None:
            return None
        value = await self.redis_client.get(key)
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    async def _set_sticky_state(self, key: str, state: str, *, ttl_seconds: int) -> None:
        if self.redis_client is None:
            return
        await self.redis_client.set(key, state.encode("utf-8"), ttl=ttl_seconds)

    def _cache_get(self, cache: dict[str, _CacheEntry], key: str) -> Any | None:
        cached = cache.get(key)
        if cached is None:
            return None
        if cached.expires_at < time.monotonic():
            cache.pop(key, None)
            return None
        return cached.value

    def _cache_set(self, cache: dict[str, _CacheEntry], key: str, value: Any) -> None:
        cache[key] = _CacheEntry(
            value=value,
            expires_at=time.monotonic() + self.cache_ttl_seconds,
        )

    @staticmethod
    def _split_binding(binding: str) -> tuple[str, str]:
        provider, separator, model_id = binding.partition(":")
        if not separator or not provider or not model_id:
            raise InvalidBindingError(
                "MODEL_BINDING_INVALID",
                f"Model binding {binding!r} must be formatted as provider:model_id.",
            )
        return provider, model_id

    @staticmethod
    def _binding_for_entry(entry: ModelCatalogEntry) -> str:
        return f"{entry.provider}:{entry.model_id}"

    @staticmethod
    def _sticky_key(workspace_id: UUID, model_id: UUID) -> str:
        return f"router:primary_sticky:{workspace_id}:{model_id}"

    @staticmethod
    def _extract_content(payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, dict):
                    return str(content)
        content = payload.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = [
                str(item.get("text"))
                for item in content
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            ]
            if text_parts:
                return "\n".join(text_parts)
        for key in ("output", "text", "response"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        return str(payload)

    @staticmethod
    def _failure_reason(exc: Exception) -> str:
        if isinstance(exc, ProviderTimeout):
            return "provider_timeout"
        if isinstance(exc, RateLimitedError):
            return "provider_rate_limited"
        return "provider_5xx"

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
