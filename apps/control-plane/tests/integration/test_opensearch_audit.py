from datetime import UTC, datetime, timedelta
from platform.search.projections import AuditSearchProjection, build_audit_query

import pytest

pytestmark = pytest.mark.asyncio


async def test_audit_search_filters_workspace_type_and_time(initialized_opensearch_client) -> None:
    projection = AuditSearchProjection(initialized_opensearch_client)
    base = datetime.now(UTC)
    for index in range(100):
        workspace = "ws-audit" if index < 60 else "ws-other"
        event_type = "AGENT_REVOKED" if index % 5 == 0 else "AGENT_PUBLISHED"
        await projection.index_event(
            {
                "event_id": f"evt-{index}",
                "event_type": event_type,
                "actor_id": f"user-{index % 7}",
                "actor_type": "user",
                "timestamp": (base - timedelta(minutes=index)).isoformat(),
                "workspace_id": workspace,
                "resource_type": "agent",
                "action": "revoke" if event_type == "AGENT_REVOKED" else "publish",
                "details": f"{event_type} details for event {index}",
            }
        )
    await initialized_opensearch_client._client.indices.refresh(index="audit-events-000001")

    result = await initialized_opensearch_client.search(
        index="audit-events-*",
        query=build_audit_query(
            event_type="AGENT_REVOKED",
            workspace_id="ws-audit",
            time_from=(base - timedelta(minutes=59)).isoformat(),
            time_to=base.isoformat(),
        ),
        workspace_id="ws-audit",
        sort=[{"timestamp": {"order": "desc"}}, {"event_id": {"order": "asc"}}],
        size=20,
    )
    assert result.hits
    assert all(hit["workspace_id"] == "ws-audit" for hit in result.hits)
    assert all(hit["event_type"] == "AGENT_REVOKED" for hit in result.hits)
    timestamps = [hit["timestamp"] for hit in result.hits]
    assert timestamps == sorted(timestamps, reverse=True)


async def test_audit_free_text_search_is_workspace_scoped(initialized_opensearch_client) -> None:
    projection = AuditSearchProjection(initialized_opensearch_client)
    await projection.index_event(
        {
            "event_id": "evt-free-text",
            "event_type": "CONNECTOR_FAILURE",
            "actor_id": "system",
            "actor_type": "service",
            "timestamp": datetime.now(UTC).isoformat(),
            "workspace_id": "ws-free",
            "resource_type": "connector",
            "action": "retry",
            "details": "connector payload checksum mismatch",
        }
    )
    await initialized_opensearch_client._client.indices.refresh(index="audit-events-000001")

    result = await initialized_opensearch_client.search(
        index="audit-events-*",
        query=build_audit_query(
            event_type=None,
            workspace_id="ws-free",
            time_from=None,
            time_to=None,
            free_text="checksum mismatch",
        ),
        workspace_id="ws-free",
        sort=[{"timestamp": {"order": "desc"}}],
        size=10,
    )
    assert result.total >= 1
    assert all(hit["workspace_id"] == "ws-free" for hit in result.hits)
