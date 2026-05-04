from __future__ import annotations

TENANT_ARCHITECTURE_JOURNEYS = {
    "J22": (
        "apps/control-plane/tests/e2e/suites/tenant_architecture/"
        "test_enterprise_tenant_provisioning.py"
    ),
    "J31": "apps/control-plane/tests/e2e/suites/tenant_architecture/test_cross_tenant_isolation.py",
    "J36": (
        "apps/control-plane/tests/e2e/suites/tenant_architecture/"
        "test_default_tenant_constraints.py"
    ),
}

# UPD-051 (104) — Data lifecycle journey registry. Lives in this directory
# (tests/e2e/journeys/) and is exercised via `make e2e-j27` and the
# `e2e-journeys` umbrella when the placeholder skip marker is removed.
DATA_LIFECYCLE_JOURNEYS = {
    "J27": "tests/e2e/journeys/test_j27_tenant_lifecycle_cancellation.py",
}

# UPD-052 (105) — Billing journey registry. Driven via `make e2e-j28`,
# `make e2e-j32`, `make e2e-j33`, `make e2e-j34` and the `e2e-journeys`
# umbrella when the placeholder skip markers are removed.
BILLING_JOURNEYS = {
    "J28": "tests/e2e/journeys/test_j28_billing_lifecycle.py",
    "J32": "tests/e2e/journeys/test_j32_webhook_idempotency.py",
    "J33": "tests/e2e/journeys/test_j33_trial_to_paid_conversion.py",
    "J34": "tests/e2e/journeys/test_j34_cancellation_reactivation.py",
}
