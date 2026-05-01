from __future__ import annotations

from datetime import UTC, datetime
from platform.context_engineering.service import ContextEngineeringService
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest


class FakePreviewRepository:
    def __init__(self, profile: SimpleNamespace) -> None:
        self.session = SimpleNamespace()
        self.profile = profile

    async def get_profile(
        self,
        workspace_id: UUID,
        profile_id: UUID,
    ) -> SimpleNamespace | None:
        if self.profile.workspace_id == workspace_id and self.profile.id == profile_id:
            return self.profile
        return None


class FakeMockLLMService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object] | None]] = []
        self.real_llm_calls_total = 0

    async def preview(
        self,
        input_text: str,
        context: dict[str, object] | None = None,
    ) -> SimpleNamespace:
        self.calls.append((input_text, context))
        return SimpleNamespace(
            output_text="mock context answer",
            completion_metadata={"model": "mock-creator-preview-v1"},
            was_fallback=False,
        )


def _service(
    repository: FakePreviewRepository,
    mock_llm_service: FakeMockLLMService,
) -> ContextEngineeringService:
    return ContextEngineeringService(
        repository=repository,  # type: ignore[arg-type]
        adapters={},
        quality_scorer=SimpleNamespace(),
        compactor=SimpleNamespace(),
        privacy_filter=SimpleNamespace(),
        object_storage=SimpleNamespace(),
        clickhouse_client=SimpleNamespace(),
        settings=SimpleNamespace(),
        event_producer=None,
        mock_llm_service=mock_llm_service,  # type: ignore[arg-type]
    )


def _profile(workspace_id: UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        workspace_id=workspace_id,
        name="Preview profile",
        source_config=[
            {
                "source_type": "long_term_memory",
                "retrieval_strategy": "semantic",
                "provenance_attribution": "memory/vector",
                "provenance_classification": "pii",
                "enabled": True,
            },
            {
                "source_type": "tool_outputs",
                "retrieval_strategy": "hybrid",
                "provenance_attribution": "tool/run",
                "provenance_classification": "public",
                "enabled": False,
            },
        ],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_preview_retrieval_invokes_mock_llm_and_returns_provenance() -> None:
    workspace_id = uuid4()
    profile = _profile(workspace_id)
    mock_llm = FakeMockLLMService()
    service = _service(FakePreviewRepository(profile), mock_llm)

    response = await service.preview_retrieval(
        workspace_id,
        profile.id,
        "memory refund policy",
        uuid4(),
    )

    assert response.mock_response == "mock context answer"
    assert response.was_fallback is False
    assert mock_llm.calls == [
        (
            "memory refund policy",
            {
                "profile_id": str(profile.id),
                "workspace_id": str(workspace_id),
                "source_count": 2,
            },
        )
    ]
    assert [source.origin for source in response.sources] == ["memory/vector", "tool/run"]
    assert response.sources[0].classification == "pii"
    assert response.sources[1].included is False
    assert response.sources[1].reason == "Source disabled in profile"


@pytest.mark.asyncio
async def test_preview_retrieval_does_not_increment_real_llm_metric() -> None:
    workspace_id = uuid4()
    profile = _profile(workspace_id)
    mock_llm = FakeMockLLMService()
    service = _service(FakePreviewRepository(profile), mock_llm)

    await service.preview_retrieval(workspace_id, profile.id, "safe query", uuid4())

    assert mock_llm.real_llm_calls_total == 0
