from __future__ import annotations

from datetime import UTC, datetime
from platform.trust.events import (
    ContentModerationProviderFailedPayload,
    ContentModerationTriggeredPayload,
    TrustEventPublisher,
    make_correlation,
    utcnow,
)
from platform.trust.exceptions import (
    ModerationCostCapExceededError,
    ModerationProviderError,
    ModerationProviderTimeoutError,
    ResidencyDisallowedProviderError,
)
from platform.trust.models import ContentModerationEvent, ContentModerationPolicy
from platform.trust.repository import TrustRepository
from platform.trust.schemas import ModerationVerdict
from platform.trust.services.moderation_action_resolver import resolve_action
from platform.trust.services.moderation_providers import ModerationProviderRegistry
from platform.trust.services.moderation_providers.base import ProviderVerdict
from typing import Any
from uuid import UUID


class ContentModerator:
    def __init__(
        self,
        *,
        repository: TrustRepository,
        providers: ModerationProviderRegistry,
        policy_engine: Any | None = None,
        residency_service: Any | None = None,
        secrets: Any | None = None,
        audit_chain: Any | None = None,
        producer: Any | None = None,
        redis: Any | None = None,
        settings: Any | None = None,
    ) -> None:
        self.repository = repository
        self.providers = providers
        self.policy_engine = policy_engine
        self.residency_service = residency_service
        self.secrets = secrets
        self.audit_chain = audit_chain
        self.events = TrustEventPublisher(producer)
        self.redis = redis
        self.settings = settings

    async def moderate_output(
        self,
        *,
        execution_id: UUID | None,
        agent_id: UUID | None,
        workspace_id: UUID,
        original_content: str,
        canonical_audit_ref: str | None = None,
        elapsed_budget_ms: int = 0,
        language: str | None = None,
        agent_fqn: str | None = None,
    ) -> ModerationVerdict:
        policy = await self.repository.get_active_moderation_policy(workspace_id)
        if policy is None:
            return ModerationVerdict(action="deliver_unchanged", content=original_content)

        if elapsed_budget_ms >= policy.per_execution_budget_ms:
            return await self._handle_provider_failure(
                policy=policy,
                workspace_id=workspace_id,
                execution_id=execution_id,
                agent_id=agent_id,
                original_content=original_content,
                audit_chain_ref=canonical_audit_ref,
                provider="budget",
                failure_type="budget_exhausted",
            )

        try:
            await self._check_cost_cap(policy, workspace_id)
        except ModerationCostCapExceededError:
            return await self._handle_provider_failure(
                policy=policy,
                workspace_id=workspace_id,
                execution_id=execution_id,
                agent_id=agent_id,
                original_content=original_content,
                audit_chain_ref=canonical_audit_ref,
                provider="cost_cap",
                failure_type="cost_cap_exceeded",
            )
        provider_names = self._provider_chain(policy, language)
        verdict: ProviderVerdict | None = None
        last_provider = provider_names[0] if provider_names else policy.primary_provider
        for provider_name in provider_names:
            last_provider = provider_name
            try:
                await self._check_residency(provider_name, workspace_id)
                provider = self.providers.get(provider_name)
                verdict = await provider.score(
                    original_content,
                    language=language,
                    categories=set(policy.categories),
                )
                if verdict.metadata.get("provider_failed"):
                    raise ModerationProviderError(provider_name)
                break
            except (ModerationProviderError, ModerationProviderTimeoutError):
                verdict = None
                await self.events.publish_content_moderation_provider_failed(
                    ContentModerationProviderFailedPayload(
                        workspace_id=workspace_id,
                        provider=provider_name,
                        failure_type="provider_error",
                        execution_id=execution_id,
                        occurred_at=utcnow(),
                    ),
                    make_correlation(workspace_id=workspace_id, execution_id=execution_id),
                )
            except ResidencyDisallowedProviderError:
                verdict = None
                await self.events.publish_content_moderation_provider_failed(
                    ContentModerationProviderFailedPayload(
                        workspace_id=workspace_id,
                        provider=provider_name,
                        failure_type="residency_disallowed",
                        execution_id=execution_id,
                        occurred_at=utcnow(),
                    ),
                    make_correlation(workspace_id=workspace_id, execution_id=execution_id),
                )
            except Exception:
                verdict = None
                await self.events.publish_content_moderation_provider_failed(
                    ContentModerationProviderFailedPayload(
                        workspace_id=workspace_id,
                        provider=provider_name,
                        failure_type="unexpected_provider_error",
                        execution_id=execution_id,
                        occurred_at=utcnow(),
                    ),
                    make_correlation(workspace_id=workspace_id, execution_id=execution_id),
                )
        if verdict is None:
            return await self._handle_provider_failure(
                policy=policy,
                workspace_id=workspace_id,
                execution_id=execution_id,
                agent_id=agent_id,
                original_content=original_content,
                audit_chain_ref=canonical_audit_ref,
                provider=last_provider,
                failure_type="provider_chain_failed",
            )

        triggered = self._triggered_categories(verdict.scores, policy.thresholds)
        if not triggered:
            event = await self._persist_event(
                workspace_id=workspace_id,
                execution_id=execution_id,
                agent_id=agent_id,
                policy=policy,
                provider=verdict.provider,
                triggered=[],
                scores=verdict.scores,
                action="none",
                language=verdict.language,
                latency_ms=verdict.latency_ms,
                audit_chain_ref=canonical_audit_ref,
            )
            return ModerationVerdict(
                action="deliver_unchanged",
                content=original_content,
                provider=verdict.provider,
                policy_id=policy.id,
                event_id=event.id,
            )

        action = resolve_action(triggered, policy)
        action = self._apply_allowlist(
            action,
            triggered,
            policy.agent_allowlist,
            agent_id=agent_id,
            agent_fqn=agent_fqn,
        )
        content = self._apply_action(action, original_content)
        event = await self._persist_event(
            workspace_id=workspace_id,
            execution_id=execution_id,
            agent_id=agent_id,
            policy=policy,
            provider=verdict.provider,
            triggered=triggered,
            scores=verdict.scores,
            action=action,
            language=verdict.language,
            latency_ms=verdict.latency_ms,
            audit_chain_ref=canonical_audit_ref,
        )
        await self.events.publish_content_moderation_triggered(
            ContentModerationTriggeredPayload(
                event_id=event.id,
                workspace_id=workspace_id,
                policy_id=policy.id,
                agent_id=agent_id,
                execution_id=execution_id,
                action_taken=action,
                triggered_categories=triggered,
                occurred_at=utcnow(),
            ),
            make_correlation(workspace_id=workspace_id, execution_id=execution_id),
        )
        if action == "flag":
            await self._publish_flag_alert(
                workspace_id=workspace_id,
                execution_id=execution_id,
                event_id=event.id,
                policy_id=policy.id,
                agent_id=agent_id,
                triggered=triggered,
                action=action,
            )
        return ModerationVerdict(
            action=action,
            content=content,
            original_content_preserved_in_audit=bool(canonical_audit_ref),
            triggered_categories=triggered,
            scores=verdict.scores,
            provider=verdict.provider,
            policy_id=policy.id,
            event_id=event.id,
            audit_chain_ref=canonical_audit_ref,
        )

    def _provider_chain(self, policy: ContentModerationPolicy, language: str | None) -> list[str]:
        pinned = policy.language_pins.get(language or "") if language else None
        names = [pinned or policy.primary_provider, policy.fallback_provider, "self_hosted"]
        result: list[str] = []
        for name in names:
            if name and name not in result and self.providers.has(name):
                result.append(name)
        return result

    async def _check_cost_cap(self, policy: ContentModerationPolicy, workspace_id: UUID) -> None:
        if self.redis is None:
            return
        now = datetime.now(UTC)
        key = f"trust:moderation_cost:{workspace_id}:{now:%Y-%m}"
        limit_cents = int(float(policy.monthly_cost_cap_eur) * 100)
        increment = getattr(self.redis, "incrby", None) or getattr(self.redis, "incr", None)
        if increment is None:
            return
        value = increment(key, 1)
        if hasattr(value, "__await__"):
            value = await value
        if int(value or 0) > limit_cents:
            raise ModerationCostCapExceededError(workspace_id)

    async def _check_residency(self, provider_name: str, workspace_id: UUID) -> None:
        if self.residency_service is None:
            return
        checker = getattr(self.residency_service, "allow_egress", None)
        if checker is None:
            return
        allowed = checker(workspace_id=workspace_id, provider=provider_name)
        if hasattr(allowed, "__await__"):
            allowed = await allowed
        if not allowed:
            raise ResidencyDisallowedProviderError(provider_name)

    async def _handle_provider_failure(
        self,
        *,
        policy: ContentModerationPolicy,
        workspace_id: UUID,
        execution_id: UUID | None,
        agent_id: UUID | None,
        original_content: str,
        audit_chain_ref: str | None,
        provider: str,
        failure_type: str,
    ) -> ModerationVerdict:
        fail_closed = policy.provider_failure_action == "fail_closed"
        action = "fail_closed_blocked" if fail_closed else "fail_open_delivered"
        event = await self._persist_event(
            workspace_id=workspace_id,
            execution_id=execution_id,
            agent_id=agent_id,
            policy=policy,
            provider=provider,
            triggered=[],
            scores={},
            action=action,
            language=None,
            latency_ms=None,
            audit_chain_ref=audit_chain_ref,
        )
        return ModerationVerdict(
            action=action,
            content=(
                "This response was blocked by content safety policy."
                if fail_closed
                else original_content
            ),
            provider=provider,
            policy_id=policy.id,
            event_id=event.id,
            audit_chain_ref=audit_chain_ref,
            reason=failure_type,
        )

    async def _persist_event(
        self,
        *,
        workspace_id: UUID,
        execution_id: UUID | None,
        agent_id: UUID | None,
        policy: ContentModerationPolicy,
        provider: str,
        triggered: list[str],
        scores: dict[str, float],
        action: str,
        language: str | None,
        latency_ms: int | None,
        audit_chain_ref: str | None,
    ) -> ContentModerationEvent:
        return await self.repository.insert_moderation_event(
            ContentModerationEvent(
                workspace_id=workspace_id,
                execution_id=execution_id,
                agent_id=agent_id,
                policy_id=policy.id,
                provider=provider,
                triggered_categories=triggered,
                scores=scores,
                action_taken=action,
                language_detected=language,
                latency_ms=latency_ms,
                audit_chain_ref=audit_chain_ref,
            )
        )

    @staticmethod
    def _triggered_categories(scores: dict[str, float], thresholds: dict[str, float]) -> list[str]:
        triggered = []
        for category, score in scores.items():
            threshold = float(thresholds.get(category, 1.0))
            if score >= threshold:
                triggered.append(category)
        return sorted(triggered)

    @staticmethod
    def _apply_action(action: str, content: str) -> str:
        if action in {"block", "fail_closed_blocked"}:
            return "This response was blocked by content safety policy."
        if action == "redact":
            return "[REDACTED]"
        return content

    @staticmethod
    def _apply_allowlist(
        action: str,
        triggered: list[str],
        allowlist: list[dict[str, Any]],
        *,
        agent_id: UUID | None,
        agent_fqn: str | None,
    ) -> str:
        for entry in allowlist:
            entry_agent_id = entry.get("agent_id")
            entry_agent_fqn = entry.get("agent_fqn")
            matches_id = agent_id is not None and str(entry_agent_id) == str(agent_id)
            matches_fqn = agent_fqn is not None and entry_agent_fqn == agent_fqn
            if not (matches_id or matches_fqn):
                continue
            allowed_categories = {str(item) for item in entry.get("categories", [])}
            if allowed_categories and not (allowed_categories & set(triggered)):
                continue
            return str(entry.get("action") or "flag")
        return action

    async def _publish_flag_alert(
        self,
        *,
        workspace_id: UUID,
        execution_id: UUID | None,
        event_id: UUID,
        policy_id: UUID,
        agent_id: UUID | None,
        triggered: list[str],
        action: str,
    ) -> None:
        producer = getattr(self.events, "producer", None)
        if producer is None:
            return
        await producer.publish(
            topic="monitor.alerts",
            key=str(workspace_id),
            event_type="trust.content_moderation.triggered",
            payload=ContentModerationTriggeredPayload(
                event_id=event_id,
                workspace_id=workspace_id,
                policy_id=policy_id,
                agent_id=agent_id,
                execution_id=execution_id,
                action_taken=action,
                triggered_categories=triggered,
                occurred_at=utcnow(),
            ).model_dump(mode="json"),
            correlation_ctx=make_correlation(workspace_id=workspace_id, execution_id=execution_id),
            source="platform.trust",
        )
