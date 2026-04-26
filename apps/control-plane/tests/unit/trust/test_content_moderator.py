from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from platform.trust.exceptions import ModerationProviderTimeoutError
from platform.trust.models import ContentModerationEvent, ContentModerationPolicy
from platform.trust.services.content_moderator import ContentModerator
from platform.trust.services.moderation_providers import ModerationProviderRegistry
from platform.trust.services.moderation_providers.base import ProviderVerdict
from typing import Any
from uuid import UUID, uuid4

import pytest


class RepositoryStub:
    def __init__(self, policy: ContentModerationPolicy | None) -> None:
        self.policy = policy
        self.events: list[ContentModerationEvent] = []

    async def get_active_moderation_policy(
        self,
        workspace_id: UUID,
    ) -> ContentModerationPolicy | None:
        assert self.policy is None or self.policy.workspace_id == workspace_id
        return self.policy

    async def insert_moderation_event(
        self,
        event: ContentModerationEvent,
    ) -> ContentModerationEvent:
        if event.id is None:
            event.id = uuid4()
        if event.created_at is None:
            event.created_at = datetime.now(UTC)
        self.events.append(event)
        return event


class ProviderStub:
    def __init__(
        self,
        *,
        name: str,
        scores: dict[str, float] | None = None,
        exc: Exception | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.name = name
        self.scores = scores or {}
        self.exc = exc
        self.metadata = metadata or {}
        self.calls = 0

    async def score(
        self,
        text: str,
        *,
        language: str | None,
        categories: set[str] | None,
    ) -> ProviderVerdict:
        del text, categories
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return ProviderVerdict(
            provider=self.name,
            scores=self.scores,
            language=language,
            metadata=self.metadata,
        )


class ProducerStub:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    async def publish(self, **kwargs: Any) -> None:
        self.published.append(kwargs)


class RedisStub:
    def __init__(self, value: int) -> None:
        self.value = value

    async def incrby(self, key: str, amount: int) -> int:
        del key, amount
        return self.value


class ResidencyStub:
    def __init__(self, denied: set[str]) -> None:
        self.denied = denied

    async def allow_egress(self, *, workspace_id: UUID, provider: str) -> bool:
        del workspace_id
        return provider not in self.denied


def _policy(
    workspace_id: UUID,
    *,
    action_map: dict[str, str] | None = None,
    thresholds: dict[str, float] | None = None,
    primary_provider: str = "primary",
    fallback_provider: str | None = "fallback",
    provider_failure_action: str = "fail_closed",
    language_pins: dict[str, str] | None = None,
    agent_allowlist: list[dict[str, Any]] | None = None,
    monthly_cost_cap_eur: Decimal = Decimal("50.00"),
) -> ContentModerationPolicy:
    return ContentModerationPolicy(
        id=uuid4(),
        workspace_id=workspace_id,
        version=1,
        active=True,
        categories=["toxicity", "hate_speech", "violence_self_harm", "pii_leakage"],
        thresholds=thresholds or {"toxicity": 0.8},
        action_map=action_map or {"toxicity": "block"},
        default_action="flag",
        primary_provider=primary_provider,
        fallback_provider=fallback_provider,
        tie_break_rule="max_score",
        provider_failure_action=provider_failure_action,
        language_pins=language_pins or {},
        agent_allowlist=agent_allowlist or [],
        monthly_cost_cap_eur=monthly_cost_cap_eur,
        per_call_timeout_ms=2000,
        per_execution_budget_ms=5000,
    )


def _moderator(
    repository: RepositoryStub,
    providers: dict[str, ProviderStub],
    *,
    producer: ProducerStub | None = None,
    redis: RedisStub | None = None,
    residency: ResidencyStub | None = None,
) -> ContentModerator:
    registry = ModerationProviderRegistry()
    for name, provider in providers.items():
        registry.register(name, provider)
    return ContentModerator(
        repository=repository,  # type: ignore[arg-type]
        providers=registry,
        producer=producer,
        redis=redis,
        residency_service=residency,
    )


@pytest.mark.asyncio
async def test_no_policy_passthrough_does_not_persist_event() -> None:
    workspace_id = uuid4()
    repo = RepositoryStub(None)
    moderator = _moderator(repo, {})

    verdict = await moderator.moderate_output(
        execution_id=uuid4(),
        agent_id=uuid4(),
        workspace_id=workspace_id,
        original_content="safe response",
    )

    assert verdict.action == "deliver_unchanged"
    assert verdict.content == "safe response"
    assert repo.events == []


@pytest.mark.asyncio
async def test_block_redact_and_flag_actions_are_applied_and_persisted() -> None:
    workspace_id = uuid4()
    producer = ProducerStub()
    scenarios = [
        ("block", {"toxicity": "block"}, {"toxicity": 0.9}, "This response was blocked"),
        ("redact", {"pii_leakage": "redact"}, {"pii_leakage": 0.7}, "[REDACTED]"),
        ("flag", {"violence_self_harm": "flag"}, {"violence_self_harm": 0.7}, "unsafe"),
    ]

    for expected_action, action_map, scores, expected_content in scenarios:
        repo = RepositoryStub(
            _policy(
                workspace_id,
                action_map=action_map,
                thresholds={next(iter(scores)): 0.5},
            )
        )
        moderator = _moderator(
            repo,
            {"primary": ProviderStub(name="primary", scores=scores)},
            producer=producer,
        )

        verdict = await moderator.moderate_output(
            execution_id=uuid4(),
            agent_id=uuid4(),
            workspace_id=workspace_id,
            original_content="unsafe",
            canonical_audit_ref="audit:1",
        )

        assert verdict.action == expected_action
        assert verdict.content.startswith(expected_content)
        assert repo.events[-1].action_taken == expected_action
        assert not hasattr(repo.events[-1], "original_content")

    alert_topics = [item["topic"] for item in producer.published]
    assert alert_topics.count("monitor.alerts") == 1


@pytest.mark.asyncio
async def test_fallback_chain_and_residency_skip_primary() -> None:
    workspace_id = uuid4()
    repo = RepositoryStub(
        _policy(
            workspace_id,
            primary_provider="primary",
            fallback_provider="fallback",
            action_map={"toxicity": "block"},
            thresholds={"toxicity": 0.8},
        )
    )
    primary = ProviderStub(name="primary", scores={"toxicity": 1.0})
    fallback = ProviderStub(name="fallback", scores={"toxicity": 0.9})
    moderator = _moderator(
        repo,
        {"primary": primary, "fallback": fallback},
        producer=ProducerStub(),
        residency=ResidencyStub({"primary"}),
    )

    verdict = await moderator.moderate_output(
        execution_id=uuid4(),
        agent_id=uuid4(),
        workspace_id=workspace_id,
        original_content="unsafe",
    )

    assert verdict.action == "block"
    assert verdict.provider == "fallback"
    assert primary.calls == 0
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_all_providers_fail_uses_provider_failure_action() -> None:
    workspace_id = uuid4()
    for failure_action, expected_action in [
        ("fail_closed", "fail_closed_blocked"),
        ("fail_open", "fail_open_delivered"),
    ]:
        repo = RepositoryStub(
            _policy(workspace_id, provider_failure_action=failure_action, fallback_provider=None)
        )
        moderator = _moderator(
            repo,
            {
                "primary": ProviderStub(
                    name="primary",
                    exc=ModerationProviderTimeoutError("primary"),
                ),
                "self_hosted": ProviderStub(
                    name="self_hosted",
                    metadata={"provider_failed": True},
                ),
            },
            producer=ProducerStub(),
        )

        verdict = await moderator.moderate_output(
            execution_id=uuid4(),
            agent_id=uuid4(),
            workspace_id=workspace_id,
            original_content="unsafe",
        )

        assert verdict.action == expected_action
        assert repo.events[-1].action_taken == expected_action


@pytest.mark.asyncio
async def test_multi_category_safer_wins_language_pin_allowlist_and_cost_cap() -> None:
    workspace_id = uuid4()
    agent_id = uuid4()
    repo = RepositoryStub(
        _policy(
            workspace_id,
            primary_provider="primary",
            language_pins={"es": "spanish"},
            action_map={"toxicity": "flag", "pii_leakage": "block"},
            thresholds={"toxicity": 0.5, "pii_leakage": 0.5},
            agent_allowlist=[
                {
                    "agent_id": str(agent_id),
                    "categories": ["toxicity", "pii_leakage"],
                    "action": "flag",
                }
            ],
        )
    )
    spanish = ProviderStub(name="spanish", scores={"toxicity": 0.8, "pii_leakage": 0.9})
    moderator = _moderator(repo, {"primary": ProviderStub(name="primary"), "spanish": spanish})

    verdict = await moderator.moderate_output(
        execution_id=uuid4(),
        agent_id=agent_id,
        workspace_id=workspace_id,
        original_content="unsafe",
        language="es",
    )

    assert verdict.provider == "spanish"
    assert verdict.action == "flag"
    assert spanish.calls == 1

    cost_repo = RepositoryStub(
        _policy(
            workspace_id,
            monthly_cost_cap_eur=Decimal("0.00"),
            provider_failure_action="fail_closed",
        )
    )
    cost_moderator = _moderator(
        cost_repo,
        {"primary": ProviderStub(name="primary", scores={"toxicity": 0.1})},
        redis=RedisStub(1),
    )

    cost_verdict = await cost_moderator.moderate_output(
        execution_id=uuid4(),
        agent_id=uuid4(),
        workspace_id=workspace_id,
        original_content="unsafe",
    )

    assert cost_verdict.action == "fail_closed_blocked"
    assert cost_verdict.reason == "cost_cap_exceeded"
