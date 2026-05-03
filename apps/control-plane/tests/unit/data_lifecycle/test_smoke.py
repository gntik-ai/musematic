"""Smoke tests for the data_lifecycle BC scaffold.

Confirms the foundational layer (models, schemas, events, exceptions,
repository, grace_calculator, cascade_dispatch) imports cleanly and the
public API surface is intact. Behavioural tests for each component will
land alongside the Phase 3-7 user-story implementations.
"""

from __future__ import annotations

import pytest

from platform.common.config import DataLifecycleSettings
from platform.data_lifecycle.events import (
    DATA_LIFECYCLE_EVENT_SCHEMAS,
    DataLifecycleEventType,
    KAFKA_TOPIC,
    register_data_lifecycle_event_types,
)
from platform.data_lifecycle.exceptions import (
    DataLifecycleError,
    DPAVirusDetected,
    SubscriptionActiveCancelFirst,
    WorkspacePendingDeletion,
)
from platform.data_lifecycle.models import (
    DataExportJob,
    DeletionJob,
    DeletionPhase,
    ExportStatus,
    ScopeType,
    SubProcessor,
)
from platform.data_lifecycle.repository import DataLifecycleRepository
from platform.data_lifecycle.schemas import (
    CancelDeletionResponse,
    SubProcessorPublic,
    TenantDeletionRequest,
    WorkspaceDeletionRequest,
)
from platform.data_lifecycle.services.grace_calculator import (
    GraceResolution,
    resolve_tenant_grace,
    resolve_workspace_grace,
)


def test_models_have_expected_table_names() -> None:
    assert DataExportJob.__tablename__ == "data_export_jobs"
    assert DeletionJob.__tablename__ == "deletion_jobs"
    assert SubProcessor.__tablename__ == "sub_processors"


def test_enums_carry_expected_values() -> None:
    assert {e.value for e in ScopeType} == {"workspace", "tenant"}
    assert {e.value for e in ExportStatus} == {
        "pending",
        "processing",
        "completed",
        "failed",
    }
    assert {e.value for e in DeletionPhase} == {
        "phase_1",
        "phase_2",
        "completed",
        "aborted",
    }


def test_kafka_topic_and_event_types() -> None:
    assert KAFKA_TOPIC == "data_lifecycle.events"
    expected_types = {
        "data_lifecycle.export.requested",
        "data_lifecycle.export.started",
        "data_lifecycle.export.completed",
        "data_lifecycle.export.failed",
        "data_lifecycle.deletion.requested",
        "data_lifecycle.deletion.phase_advanced",
        "data_lifecycle.deletion.aborted",
        "data_lifecycle.deletion.completed",
        "data_lifecycle.dpa.uploaded",
        "data_lifecycle.dpa.removed",
        "data_lifecycle.sub_processor.added",
        "data_lifecycle.sub_processor.modified",
        "data_lifecycle.sub_processor.removed",
        "data_lifecycle.backup.purge_completed",
    }
    assert {e.value for e in DataLifecycleEventType} == expected_types
    assert set(DATA_LIFECYCLE_EVENT_SCHEMAS.keys()) == expected_types


def test_register_data_lifecycle_event_types_is_idempotent() -> None:
    """The registry deduplicates on event type, so calling twice is safe."""

    register_data_lifecycle_event_types()
    register_data_lifecycle_event_types()  # must not raise


def test_exception_status_codes_match_contract() -> None:
    assert DataLifecycleError.status_code == 400
    assert WorkspacePendingDeletion.status_code == 423
    assert DPAVirusDetected.status_code == 422
    assert SubscriptionActiveCancelFirst.status_code == 409


def test_cancel_deletion_response_is_anti_enumeration() -> None:
    """The response is identical regardless of token outcome (R10)."""

    body = CancelDeletionResponse().message
    assert body.startswith("If the link was valid")


def test_workspace_deletion_request_validates_typed_confirmation() -> None:
    req = WorkspaceDeletionRequest(typed_confirmation="acme-pro")
    assert req.typed_confirmation == "acme-pro"


def test_tenant_deletion_request_grace_bounds_enforced() -> None:
    # Within bounds: 7..90.
    TenantDeletionRequest(
        typed_confirmation="delete tenant acme",
        reason="contract end",
        grace_period_days=14,
    )
    # Below floor.
    with pytest.raises(Exception):  # pydantic ValidationError
        TenantDeletionRequest(
            typed_confirmation="delete tenant acme",
            reason="too short",
            grace_period_days=3,
        )
    # Above ceiling.
    with pytest.raises(Exception):
        TenantDeletionRequest(
            typed_confirmation="delete tenant acme",
            reason="too long",
            grace_period_days=120,
        )


def test_grace_calculator_default_workspace() -> None:
    s = DataLifecycleSettings()
    r = resolve_workspace_grace(settings=s, tenant_contract_metadata=None)
    assert r == GraceResolution(days=7, source="default")


def test_grace_calculator_tenant_override_wins() -> None:
    s = DataLifecycleSettings()
    r = resolve_tenant_grace(
        settings=s,
        tenant_contract_metadata={"deletion_grace_period_days": 45},
    )
    assert r.days == 45
    assert r.source == "tenant_override"


def test_grace_calculator_request_override_beats_tenant() -> None:
    s = DataLifecycleSettings()
    r = resolve_tenant_grace(
        settings=s,
        tenant_contract_metadata={"deletion_grace_period_days": 45},
        request_override_days=21,
    )
    assert r.days == 21
    assert r.source == "request_override"


def test_grace_calculator_rejects_out_of_bounds_override() -> None:
    s = DataLifecycleSettings()
    with pytest.raises(Exception):
        resolve_workspace_grace(
            settings=s,
            tenant_contract_metadata={"deletion_grace_period_days": 200},
        )


def test_repository_class_exposes_expected_methods() -> None:
    expected = {
        "create_export_job",
        "get_export_job",
        "find_active_export_for_scope",
        "count_recent_exports_for_scope",
        "list_export_jobs_for_scope",
        "update_export_status",
        "create_deletion_job",
        "get_deletion_job",
        "find_active_deletion_for_scope",
        "find_deletion_by_cancel_token_hash",
        "list_grace_expired_phase_1_jobs",
        "update_deletion_phase",
        "extend_grace",
        "list_sub_processors_active",
        "list_sub_processors_all",
        "get_sub_processor",
        "get_sub_processor_by_name",
        "insert_sub_processor",
        "update_sub_processor",
        "soft_delete_sub_processor",
        "latest_sub_processors_change",
    }
    actual = {m for m in dir(DataLifecycleRepository) if not m.startswith("_")}
    missing = expected - actual
    assert not missing, f"repository missing methods: {missing}"


def test_subprocessor_public_omits_notes_field() -> None:
    """Public payload must not expose operator notes."""

    fields = set(SubProcessorPublic.model_fields.keys())
    assert "notes" not in fields
    assert "name" in fields and "category" in fields and "data_categories" in fields
