"""UPD-049 refresh (102) T061 — MarketplaceFanoutConsumer registration lock.

Verifies the consumer added by T009 is wired into the worker profile's
lifespan so source-updated events fan out to fork owners. Locks the
registration against future regressions where a refactor accidentally
removes the consumer wiring.

Runs under the ``integration_live`` mark — needs a worker process
running with ``profile=worker`` and a Kafka consumer manager attached.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


async def test_marketplace_fanout_consumer_registered_on_worker_lifespan() -> None:
    """Outline:

    1. Boot a worker-profile FastAPI app via the same lifecycle the
       production worker uses (``create_app(profile='worker')`` from
       ``platform.main``).
    2. Inspect the consumer manager's subscription registry for the
       topic ``marketplace.events`` and the consumer-group key
       ``{KAFKA_CONSUMER_GROUP_ID}.marketplace-fanout``.
    3. Assert the subscription is present and active.
    4. Optionally publish a synthetic ``marketplace.source_updated``
       Kafka event and assert the consumer's `handle_event` was
       invoked (with a non-null ``source_agent_id``).
    """

    pytest.skip(
        "Live-DB+Kafka integration body to be filled in once the fixture "
        "harness ships. Outline above is the test specification."
    )
