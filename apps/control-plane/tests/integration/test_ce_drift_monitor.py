from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.context_engineering.adapters import build_default_adapters
from platform.context_engineering.compactor import ContextCompactor
from platform.context_engineering.drift_monitor import DriftMonitorTask
from platform.context_engineering.privacy_filter import PrivacyFilter
from platform.context_engineering.quality_scorer import QualityScorer
from platform.context_engineering.service import ContextEngineeringService
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.analytics_support import ClickHouseClientStub
from tests.context_engineering_support import (
    EventProducerStub,
    MemoryContextRepository,
    PoliciesServiceStub,
    WorkspaceRepoStub,
    WorkspacesServiceStub,
)
from tests.registry_support import ObjectStorageStub


@pytest.mark.asyncio
async def test_drift_monitor_creates_alert_and_avoids_duplicates() -> None:
    workspace_id = uuid4()
    clickhouse = ClickHouseClientStub(
        query_responses=[
            [
                {
                    "workspace_id": str(workspace_id),
                    "agent_fqn": "finance:agent",
                    "historical_mean": 0.8,
                    "historical_stddev": 0.1,
                    "recent_mean": 0.4,
                }
            ],
            [
                {
                    "workspace_id": str(workspace_id),
                    "agent_fqn": "finance:agent",
                    "historical_mean": 0.8,
                    "historical_stddev": 0.1,
                    "recent_mean": 0.4,
                }
            ],
        ]
    )
    producer = EventProducerStub()
    service = ContextEngineeringService(
        repository=MemoryContextRepository(),
        adapters=build_default_adapters(),
        quality_scorer=QualityScorer(),
        compactor=ContextCompactor(),
        privacy_filter=PrivacyFilter(policies_service=PoliciesServiceStub()),
        object_storage=ObjectStorageStub(),
        clickhouse_client=clickhouse,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        event_producer=producer,
        workspaces_service=WorkspacesServiceStub(
            workspace_ids=[workspace_id],
            repo=WorkspaceRepoStub(
                workspace=SimpleNamespace(
                    id=workspace_id,
                    name="Finance",
                    description="Finance",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            ),
        ),
    )

    created = await DriftMonitorTask(service).run()
    created_again = await service.run_drift_analysis()

    assert created == 1
    assert created_again == 0
    assert len(service.repository.alerts) == 1  # type: ignore[attr-defined]
    assert any(
        item["event_type"] == "context_engineering.drift.detected" for item in producer.published
    )
