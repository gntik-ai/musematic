"""UPD-049 refresh (102) T060 — fork tool-dependency cross-check.

Spec coverage: T054. Verifies that the response's
``tool_dependencies_missing`` array names ONLY the tools NOT registered
in the consumer's tenant (matched by display_name or endpoint_url),
not the full source ``mcp_server_refs`` list.

Runs under the ``integration_live`` mark.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


async def test_fork_tool_dependency_missing_filtered_by_consumer_tenant() -> None:
    """Outline:

    1. Seed:
       * Default-tenant published public agent with
         ``mcp_server_refs = ['anthropic-mcp', 'github-mcp', 'private-tool']``.
       * Acme Enterprise tenant with consume flag enabled.
       * Acme has registered MCP servers with display_name='anthropic-mcp'
         and display_name='github-mcp'; 'private-tool' is NOT registered.
    2. Authenticate as an Acme user.
    3. POST /api/v1/registry/agents/{public_agent_id}/fork.
    4. Assert HTTP 200.
    5. Assert response body ``tool_dependencies_missing == ['private-tool']``.
       The two registered tools MUST NOT appear in the missing list.
    """

    pytest.skip(
        "Live-DB integration body to be filled in once the fixture harness "
        "ships. Outline above is the test specification."
    )
