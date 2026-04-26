from __future__ import annotations

from typing import Final

COST_TYPES: Final[tuple[str, ...]] = ("model", "compute", "storage", "overhead")
BUDGET_PERIOD_TYPES: Final[tuple[str, ...]] = ("daily", "weekly", "monthly")
ANOMALY_TYPES: Final[tuple[str, ...]] = ("sudden_spike", "sustained_deviation")
ANOMALY_SEVERITIES: Final[tuple[str, ...]] = ("low", "medium", "high", "critical")
ANOMALY_STATES: Final[tuple[str, ...]] = ("open", "acknowledged", "resolved")
BLOCK_REASON_COST_BUDGET: Final[str] = "workspace_cost_budget_exceeded"
KAFKA_TOPIC: Final[str] = "cost-governance.events"

