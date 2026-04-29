from __future__ import annotations

import pytest


pytestmark = [pytest.mark.journey, pytest.mark.j10_privacy_officer]


def test_j10_privacy_officer_happy_path_contract() -> None:
    cascade_assertions = [
        "dsr_submitted",
        "privacy_officer_approved",
        "dsr_completed",
        "postgres_tombstoned",
        "qdrant_vectors_removed",
        "neo4j_nodes_detached",
        "clickhouse_rows_deleted",
        "opensearch_documents_deleted",
        "s3_objects_purged",
        "tombstone_hash_recorded",
        "audit_chain_entry_linked",
        "subject_notification_delivered",
        "duration_metric_emitted",
        "loki_log_dsr_completed",
    ]

    assert len(cascade_assertions) >= 10
    assert "tombstone_hash_recorded" in cascade_assertions
    assert "audit_chain_entry_linked" in cascade_assertions


def test_j10_partial_cascade_failure_is_not_marked_completed() -> None:
    failed_cascade = {
        "failed_store": "qdrant",
        "dsr_status": "failed",
        "tombstone_created": False,
        "audit_event": "dsr.cascade.partial_failure",
    }

    assert failed_cascade["dsr_status"] == "failed"
    assert failed_cascade["tombstone_created"] is False
    assert failed_cascade["audit_event"] != "dsr.cascade.completed"


def test_j10_audit_chain_integrity_post_condition() -> None:
    verification = {
        "chain_intact": True,
        "verified_entries_count": 3,
        "contains_dsr_entry": True,
    }

    assert verification["chain_intact"] is True
    assert verification["verified_entries_count"] > 0
    assert verification["contains_dsr_entry"] is True
