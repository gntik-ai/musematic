"""UPD-049 refresh (102) T059 — fork quota enforcement.

Spec coverage: contracts/fork-rest.md, T053. Verifies that a fork
attempt by a consumer whose plan is at the agent-publish cap returns
HTTP 402 with code ``BILLING_QUOTA_EXCEEDED`` (per the existing
billing exception surface).

Runs under the ``integration_live`` mark.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


async def test_fork_refused_when_consumer_at_agent_publish_cap() -> None:
    """Outline:

    1. Seed:
       * Default-tenant published public agent.
       * Acme Enterprise tenant with consume_public_marketplace=true.
       * Acme's plan_version sets agent_publish quota=N; pre-create N
         agents in Acme's workspace so the next publish is at-cap.
    2. Authenticate as an Acme user with publish permission.
    3. POST /api/v1/registry/agents/{public_agent_id}/fork with
       target_scope='workspace'.
    4. Assert HTTP 402.
    5. Assert response body code == 'BILLING_QUOTA_EXCEEDED' and
       details.quota_name == 'agent_publish'.
    6. Assert no fork row was created in Acme's workspace
       (SELECT count(*) FROM registry_agent_profiles WHERE
       forked_from_agent_id = source.id AND tenant_id = acme_id == 0).
    """

    pytest.skip(
        "Live-DB integration body to be filled in once the fixture harness "
        "ships. Outline above is the test specification."
    )
