"""UPD-049 refresh (102) T049 — parity probe is invisible in production.

Asserts the constitutional rule 26 behaviour: with
``FEATURE_E2E_MODE=false``, the endpoint MUST return 404 with NO body
(not 403, not 422 — completely invisible).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


async def test_parity_probe_returns_404_when_e2e_mode_disabled() -> None:
    """Outline:

    1. Configure the test process with ``FEATURE_E2E_MODE=false``.
    2. Authenticate as superadmin.
    3. GET ``/api/v1/admin/marketplace-review/parity-probe?query=anything&subject_tenant_id=<any-uuid>``.
    4. Assert HTTP 404.
    5. Assert response body is empty (no JSON, no error code).
    6. Assert no audit-chain entry was emitted (the probe never ran).
    """

    pytest.skip(
        "Live-DB integration body to be filled in once the fixture harness "
        "ships. Outline above is the test specification."
    )
