"""J27 — Tenant Lifecycle Cancellation journey (UPD-051 / T097).

Per quickstart.md § Journey J27: end-to-end real-cluster journey
crossing all 5 user stories of UPD-051. Asserts via real Loki +
Prometheus queries (rule 26):

1. Bootstrap tenant `j27-acme` with two workspaces.
2. Workspace owner of `j27-acme/main` requests workspace export →
   email arrives → download URL works.
3. Super admin requests tenant export → URL + OTP delivered out-of-band.
4. Super admin schedules tenant deletion (2PA-gated, subscription
   preflight). Verify final export job created.
5. Fast-forward grace → cascade dispatches across 6 stores +
   (FEATURE_UPD053_DNS_TEARDOWN=true) DNS teardown. Tombstone present.
6. Audit chain integrity: `python tools/verify_audit_chain.py
   --tenant j27-acme` exits 0.
7. Loki query: `{service="control-plane",bounded_context="data_lifecycle"}
   |= "tenant_deletion_completed"` returns the expected log line.
8. Prometheus: `data_lifecycle_export_duration_seconds` p95 ≤ 60 min.
9. Backup-purge T+30 (CI fast-forwards wall clock):
   `data_lifecycle.backup.purge_completed` event observed; KMS key
   destroyed.

Skip-marked until make dev-up + UPD-053 DNS teardown service land.
"""

from __future__ import annotations

import pytest

# UPD-054 (107) — extended to the journey-template marker set so the
# smoke-test contract test passes. The skip-marker remains until the
# full body lands per spec.md US1 acceptance scenario 4.
pytestmark = [
    pytest.mark.journey,
    pytest.mark.j27,
    pytest.mark.timeout(480),
    pytest.mark.skip(
        reason=(
            "J27 Tenant Lifecycle Cancellation journey — requires make dev-up "
            "+ FEATURE_UPD053_DNS_TEARDOWN=true. Body lands during UPD-054 US1 "
            "implementation (specs/107-saas-e2e-journeys/tasks.md T016)."
        )
    ),
]


def test_j27_tenant_lifecycle_cancellation() -> None:
    """Placeholder so pytest collection sees J27 in the journey suite."""
