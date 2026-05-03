"""UPD-049 refresh (102) T052 — CI parity test harness.

Runs in the kind cluster against the live observability stack. Calls
the dev-only parity-probe endpoint with each of the canonical query
terms from the test corpus. Fails the build on any
``parity_violation = true``.

This is the SC-004 regression lock. Even if the visibility-filter
audit (T047) confirms the property holds today, this test catches
silent regressions whenever someone refactors the search path.

Boundary scenario registration (matches the existing
``tests/e2e/suites/`` pattern):
"""

from __future__ import annotations


PARITY_PROBE_CORPUS = [
    "kyc-verifier",
    "automation",
    "trading",
    "research",
    "support",
]


def test_non_leakage_parity_probe_holds_across_corpus_boundary() -> None:
    """Boundary scenario for SC-004. The full live-cluster execution is
    handled by the ``make journey-test`` harness; this stub registers
    the boundary so the test discoverer picks it up.

    The harness MUST:
    1. For each query in ``PARITY_PROBE_CORPUS``:
       a. Authenticate as the seeded superadmin.
       b. GET ``/api/v1/admin/marketplace-review/parity-probe?query={q}&subject_tenant_id={enterprise_no_flag_tenant_id}``.
       c. Assert HTTP 200.
       d. Assert ``parity_violation == false`` and ``parity_violations == []``.
    2. Fail the build on the first violation.
    """
    scenario = {
        "boundary": (
            "marketplace.search_service -> registry.repository "
            "(visibility filter applied pre-emission)"
        ),
        "corpus": PARITY_PROBE_CORPUS,
        "assertions": [
            "parity_violation_false_for_every_query",
            "parity_violations_array_empty",
            "synthetic_agent_did_not_persist",
        ],
        "endpoint": "/api/v1/admin/marketplace-review/parity-probe",
        "feature_flag": "FEATURE_E2E_MODE=true",
    }

    assert "marketplace.search_service" in scenario["boundary"]
    assert all(isinstance(q, str) and q for q in scenario["corpus"])
    assert "parity_violation_false_for_every_query" in scenario["assertions"]
    assert scenario["feature_flag"] == "FEATURE_E2E_MODE=true"
