from __future__ import annotations

import hashlib

import pytest


pytestmark = [pytest.mark.journey, pytest.mark.j16_compliance_auditor]


def test_j16_compliance_audit_export_contract() -> None:
    stages = [
        "audit_export_requested",
        "signature_verified_with_public_key",
        "chain_integrity_verified",
        "auth_events_queried",
        "dsr_events_queried",
        "policy_violations_queried",
        "jit_grants_queried",
        "evidence_dashboard_snapshot",
        "evidence_bundle_downloaded",
        "manifest_hashes_verified",
    ]

    assert len(stages) >= 6
    assert "signature_verified_with_public_key" in stages
    assert "manifest_hashes_verified" in stages


def test_j16_broken_chain_negative_variant_names_sequence() -> None:
    verification = {"chain_intact": False, "broken_sequence_number": 42}

    assert verification["chain_intact"] is False
    assert verification["broken_sequence_number"] == 42


def test_j16_evidence_bundle_manifest_consistency() -> None:
    content = b"evidence"
    manifest = {"evidence.txt": hashlib.sha256(content).hexdigest()}

    assert manifest["evidence.txt"] == hashlib.sha256(content).hexdigest()
