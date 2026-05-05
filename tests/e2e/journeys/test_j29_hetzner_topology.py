"""J29 — Hetzner Topology Provisioning journey (UPD-053 / US1+US2).

Per spec.md § US1: end-to-end real-cluster journey provisioning
``musematic-prod`` from an empty Hetzner Cloud project, asserting:

1. ``terraform apply`` completes for ``terraform/environments/production``
   without errors and produces ``lb_ipv4`` / ``lb_ipv6`` / ``zone_id`` outputs.
2. Cluster bootstrap (kubeadm via Ansible playbook) leaves 1 control plane
   + 3 workers Ready.
3. ``helm install platform deploy/helm/platform -f values.prod.yaml`` succeeds
   with all platform deployments reaching Ready inside 10 minutes.
4. cert-manager wildcard cert ``wildcard-musematic-ai`` reports
   Ready=True within 5 minutes of helm install completing.
5. ``curl https://app.musematic.ai/healthz`` returns 200 with a non-self-
   signed cert chain. Same for api.musematic.ai and grafana.musematic.ai.
6. Total wall-clock from ``terraform apply`` start to fully healthy
   cluster: ≤ 30 minutes (SC-001).

The dev counterpart (US2) is asserted by
``tests/e2e/suites/hetzner_topology/test_dev_isolation.py``.

Skip-marked by default — gated on ``RUN_J29=1`` so CI never accidentally
provisions a real Hetzner project. Operators run this manually after
seeding Hetzner credentials and accepting the cost (~€80 for the few
hours the test cluster lives).
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_J29", "0") != "1",
    reason=(
        "J29 Hetzner Topology journey — provisions a real Hetzner Cloud "
        "project. Set RUN_J29=1 + seed Hetzner Cloud + DNS API tokens in "
        "Vault under secret/musematic/prod/{hcloud,dns/hetzner}/api-token "
        "before running. Documented in "
        "docs/operations/hetzner-cluster-provisioning.md."
    ),
)


def test_j29_hetzner_topology_provisioning() -> None:
    """Live-Hetzner journey scaffold; body lands when the J29 helpers
    (terraform-driver, ansible-driver, helm-driver) are wired into the
    test harness. The gates above keep CI safe.
    """
    pytest.fail(
        "J29 journey body not implemented — fixture wiring tracked under "
        "specs/106-hetzner-clusters/tasks.md T080.",
    )
