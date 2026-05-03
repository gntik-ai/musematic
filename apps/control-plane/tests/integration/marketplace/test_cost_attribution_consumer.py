"""UPD-049 refresh (102) T041 — cost attribution to consumer tenant.

Spec coverage: spec.md FR-741.4 / SC-005, research R14.

Verifies that when an Enterprise tenant with the
``consume_public_marketplace`` flag invokes a public-default-tenant
marketplace agent, the resulting ``cost_events`` row in ClickHouse has
``tenant_id = consumer_tenant_uuid`` (Acme), NOT ``tenant_id =
default_tenant_uuid`` (the publisher).

This test locks the property — it is otherwise automatic via the
existing cost-attribution path (the execution context's tenant_id is
the consumer's), but a future refactor that moves cost-event-emit
upstream of execution-context binding could regress it silently.
SC-005 names production billing reports as zero-defect, so the
regression must be locked.

Runs against the live-DB+Kafka+ClickHouse fixture provided by feature
071. The ``integration_live`` mark is selected by the orchestrator's
``make integration-test`` target.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


async def test_consumer_runs_public_agent_cost_attributes_to_consumer() -> None:
    """End-to-end cost-attribution lock for SC-005.

    Implementation outline (live-DB+Kafka+ClickHouse fixture):

    1. Seed:
       * Default-tenant Pro user publishes a public agent — approved.
       * Acme Enterprise tenant has ``consume_public_marketplace=true``.
       * Acme user U_A authenticated via ``http_client``.
    2. Capture ClickHouse offset on ``cost_events`` (e.g.
       ``SELECT max(received_at) FROM cost_events``).
    3. POST ``/api/v1/registry/agents/{public_agent_id}/invoke`` as U_A
       (or whichever invocation surface is canonical) — assert 200.
    4. Wait for the Kafka → ClickHouse pipeline to flush
       (``kafka_consumer.flush()`` or poll up to N seconds).
    5. SELECT FROM cost_events WHERE received_at > offset AND
       execution_id = <captured_id>.
    6. Assert exactly one row, with ``tenant_id = acme_tenant_uuid``
       (the consumer), NOT the default-tenant uuid (the publisher).
    """

    pytest.skip(
        "Live-DB+Kafka+ClickHouse integration body to be filled in once "
        "the fixture harness ships. The 6-step outline above is the test "
        "specification."
    )
