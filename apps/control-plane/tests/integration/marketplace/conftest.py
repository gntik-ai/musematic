from __future__ import annotations

from uuid import uuid4

import pytest
from tests.marketplace_support import (
    ClickHouseClientStub,
    OpenSearchClientStub,
    QdrantClientStub,
    WorkspacesServiceStub,
    build_quality_aggregate,
    build_rating,
)


@pytest.fixture
def mock_opensearch_client() -> OpenSearchClientStub:
    return OpenSearchClientStub()


@pytest.fixture
def mock_qdrant_client() -> QdrantClientStub:
    return QdrantClientStub(search_results=[])


@pytest.fixture
def mock_clickhouse_client() -> ClickHouseClientStub:
    return ClickHouseClientStub(responses=[])


@pytest.fixture
def mock_workspace_service() -> WorkspacesServiceStub:
    return WorkspacesServiceStub()


@pytest.fixture
def sample_quality_aggregate():
    return build_quality_aggregate(agent_id=uuid4())


@pytest.fixture
def sample_agent_rating():
    return build_rating(agent_id=uuid4(), user_id=uuid4(), score=5)
