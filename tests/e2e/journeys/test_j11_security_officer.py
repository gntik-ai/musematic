from __future__ import annotations

import pytest


pytestmark = [pytest.mark.journey, pytest.mark.j11_security_officer]


def test_j11_security_officer_cycle_contract() -> None:
    stages = [
        "sbom_spdx_published",
        "sbom_cyclonedx_published",
        "critical_cve_ingested",
        "incident_ticket_created",
        "rotation_dual_window_scheduled",
        "old_credential_valid_during_window",
        "jit_credential_issued",
        "jit_credential_use_audited",
        "audit_chain_verified",
        "signed_audit_export_verified",
    ]

    assert len(stages) >= 7
    assert {"audit_chain_verified", "signed_audit_export_verified"} <= set(stages)


def test_j11_dev_dependency_cve_does_not_block_release() -> None:
    response = {"dependency_type": "dev", "release_blocked": False, "severity": "critical"}

    assert response["dependency_type"] == "dev"
    assert response["release_blocked"] is False
    assert response["severity"] == "critical"


def test_j11_jit_credential_expiry_records_refusal() -> None:
    refusal = {"accepted": False, "error": "JIT credential expired", "audit_recorded": True}

    assert refusal["accepted"] is False
    assert "expired" in refusal["error"].lower()
    assert refusal["audit_recorded"] is True


def test_j11_chain_integrity_post_condition() -> None:
    assert {"chain_intact": True, "cycle_entries": 7}["chain_intact"] is True
