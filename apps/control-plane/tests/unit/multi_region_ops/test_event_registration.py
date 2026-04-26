from __future__ import annotations

from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext
from platform.common.events.registry import event_registry
from platform.multi_region_ops.constants import (
    MAINTENANCE_MODE_DISABLED_EVENT,
    MAINTENANCE_MODE_ENABLED_EVENT,
    REGION_FAILOVER_COMPLETED_EVENT,
    REGION_FAILOVER_INITIATED_EVENT,
    REGION_REPLICATION_LAG_EVENT,
)
from platform.multi_region_ops.events import (
    MaintenanceModeDisabledPayload,
    register_multi_region_ops_event_types,
)
from uuid import uuid4


def test_register_multi_region_ops_event_types() -> None:
    register_multi_region_ops_event_types()

    for event_type in (
        REGION_REPLICATION_LAG_EVENT,
        REGION_FAILOVER_INITIATED_EVENT,
        REGION_FAILOVER_COMPLETED_EVENT,
        MAINTENANCE_MODE_ENABLED_EVENT,
        MAINTENANCE_MODE_DISABLED_EVENT,
    ):
        assert event_registry.is_registered(event_type)


def test_payload_schema_validates_correlation_context() -> None:
    register_multi_region_ops_event_types()
    payload = MaintenanceModeDisabledPayload(
        window_id=uuid4(),
        disabled_at=datetime.now(UTC),
        disable_kind="manual",
    )
    correlation = CorrelationContext(correlation_id=uuid4())

    assert payload.window_id
    assert correlation.correlation_id
