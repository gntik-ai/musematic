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
