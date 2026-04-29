from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.interactions.events import AttentionRequestedPayload
from platform.notifications.models import DeliveryOutcome
from platform.notifications.service import AlertService
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from tests.auth_support import RecordingProducer


class _RateLimitResult:
    allowed = True


class _Redis:
    async def check_rate_limit(
        self,
        resource: str,
        key: str,
        limit: int,
        window_ms: int,
    ) -> _RateLimitResult:
        del resource, key, limit, window_ms
        return _RateLimitResult()


class _Accounts:
    def __init__(self, user: SimpleNamespace) -> None:
        self.user = user

    async def get_user_by_id(self, user_id: UUID) -> SimpleNamespace | None:
        return self.user if self.user.id == user_id else None

    async def get_user_by_email(self, email: str) -> SimpleNamespace | None:
        return self.user if self.user.email == email else None


class _Repo:
    def __init__(self) -> None:
        self.created: list[SimpleNamespace] = []

    async def get_settings(self, user_id: UUID) -> None:
        del user_id
        return None

    async def create_alert(
        self,
        *,
        user_id: UUID,
        interaction_id: UUID | None,
        source_reference: dict[str, object] | None,
        alert_type: str,
        title: str,
        body: str | None,
        urgency: str,
        delivery_method: object | None = None,
    ) -> SimpleNamespace:
        del delivery_method
        now = datetime.now(UTC)
        alert = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            interaction_id=interaction_id,
            source_reference=source_reference,
            alert_type=alert_type,
            title=title,
            body=body,
            urgency=urgency,
            read=False,
            created_at=now,
            updated_at=now,
            delivery_outcome=None,
        )
        self.created.append(alert)
        return alert


class _Deliverer:
    async def send(self, *args: object, **kwargs: object) -> DeliveryOutcome:
        del args, kwargs
        return DeliveryOutcome.success


class _Localization:
    def __init__(self, language: str | Exception) -> None:
        self.language = language
        self.calls: list[UUID] = []

    async def get_user_language(self, user_id: UUID) -> str:
        self.calls.append(user_id)
        if isinstance(self.language, Exception):
            raise self.language
        return self.language


def _service(
    user: SimpleNamespace,
    localization: _Localization,
) -> tuple[AlertService, _Repo, RecordingProducer]:
    repo = _Repo()
    producer = RecordingProducer()
    return (
        AlertService(
            repo=repo,  # type: ignore[arg-type]
            accounts_repo=_Accounts(user),  # type: ignore[arg-type]
            workspaces_service=None,
            redis=_Redis(),  # type: ignore[arg-type]
            producer=producer,
            settings=PlatformSettings(),
            email_deliverer=_Deliverer(),  # type: ignore[arg-type]
            webhook_deliverer=_Deliverer(),  # type: ignore[arg-type]
            localization_service=localization,
        ),
        repo,
        producer,
    )


def _attention_payload(user: SimpleNamespace) -> AttentionRequestedPayload:
    return AttentionRequestedPayload(
        request_id=uuid4(),
        workspace_id=uuid4(),
        source_agent_fqn="agents:triage",
        target_identity=user.email,
        urgency="high",
        related_interaction_id=uuid4(),
        related_goal_id=None,
        context_summary="Runbook ABC requires approval",
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_attention_notification_uses_recipient_language_for_platform_strings() -> None:
    user = SimpleNamespace(id=uuid4(), email="operator@example.com")
    localization = _Localization("es")
    service, repo, producer = _service(user, localization)

    alert = await service.process_attention_request(_attention_payload(user))

    assert alert is not None
    assert localization.calls == [user.id]
    assert repo.created[0].title == "Atención solicitada por agents:triage"
    assert repo.created[0].body == "Runbook ABC requires approval"
    assert producer.events[-1]["payload"]["title"] == "Atención solicitada por agents:triage"
    assert producer.events[-1]["payload"]["body"] == "Runbook ABC requires approval"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_notification_language_resolution_failure_falls_back_to_english(
    caplog: pytest.LogCaptureFixture,
) -> None:
    user = SimpleNamespace(id=uuid4(), email="operator@example.com")
    localization = _Localization(RuntimeError("localization unavailable"))
    service, repo, producer = _service(user, localization)

    with caplog.at_level("WARNING"):
        alert = await service.process_attention_request(_attention_payload(user))

    assert alert is not None
    assert repo.created[0].title == "Attention requested by agents:triage"
    assert repo.created[0].body == "Runbook ABC requires approval"
    assert producer.events[-1]["payload"]["title"] == "Attention requested by agents:triage"
    assert "Falling back to default notification language" in caplog.text
