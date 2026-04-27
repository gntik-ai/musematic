from __future__ import annotations

REQUIRED_FIELDS = ("timestamp", "level", "service", "bounded_context", "message")
OPTIONAL_FIELDS = (
    "trace_id",
    "span_id",
    "correlation_id",
    "workspace_id",
    "goal_id",
    "user_id",
    "execution_id",
)
LOG_LEVELS = ("debug", "info", "warn", "error", "fatal")
LOKI_LABEL_ALLOWLIST = ("service", "bounded_context", "level", "namespace", "pod", "container")
HIGH_CARDINALITY_FORBIDDEN_LABELS = (
    "workspace_id",
    "user_id",
    "goal_id",
    "correlation_id",
    "trace_id",
    "execution_id",
)
