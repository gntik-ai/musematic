"""UPD-049 refresh (102) T048 — non-leakage parity (SC-004) end-to-end.

For each of 5 canonical query terms in the test corpus, drives the
dev-only parity-probe endpoint as a fresh non-default-tenant subject
and asserts ``parity_violation = false`` and ``parity_violations = []``.

Runs under the ``integration_live`` mark + a probe-enabled overlay
(``FEATURE_E2E_MODE=true``).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


PARITY_PROBE_CORPUS = [
    "kyc-verifier",
    "automation",
    "trading",
    "research",
    "support",
]


@pytest.mark.parametrize("query", PARITY_PROBE_CORPUS)
async def test_parity_probe_holds_for_canonical_query(query: str) -> None:
    """For each query, run the probe as a no-consume-flag Enterprise
    tenant and assert no parity violation.

    Outline:

    1. Seed: a fresh Enterprise tenant `acme_no_flag` with
       ``feature_flags['consume_public_marketplace']=False`` (or absent).
    2. Authenticate as superadmin.
    3. GET ``/api/v1/admin/marketplace-review/parity-probe?query={q}&subject_tenant_id={acme_id}``.
    4. Assert HTTP 200.
    5. Assert ``parity_violation == false``.
    6. Assert ``parity_violations == []``.
    7. Assert the synthetic agent did NOT persist
       (``SELECT FROM registry_agent_profiles WHERE fqn LIKE '_parity_probe:%'``
       returns 0 rows).
    """

    pytest.skip(
        "Live-DB+Kafka integration body to be filled in once the fixture "
        "harness ships. Outline above is the test specification."
    )
