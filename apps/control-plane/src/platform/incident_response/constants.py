from __future__ import annotations

INCIDENT_SEVERITIES = ("critical", "high", "warning", "info")
INCIDENT_STATUSES = ("open", "acknowledged", "resolved", "auto_resolved")
PAGING_PROVIDERS = ("pagerduty", "opsgenie", "victorops")
RUNBOOK_STATUSES = ("active", "retired")
POSTMORTEM_STATUSES = ("draft", "published", "distributed")
TIMELINE_SOURCES = ("audit_chain", "execution_journal", "kafka")

EXTERNAL_ALERT_STATUSES = ("pending", "delivered", "failed", "resolved")
TIMELINE_COVERAGE_STATES = ("complete", "partial", "unavailable")

KAFKA_TOPIC = "incident_response.events"
INCIDENT_TRIGGERED_EVENT = "incident.triggered"
INCIDENT_RESOLVED_EVENT = "incident.resolved"

VAULT_INTEGRATION_PATH_TEMPLATE = "incident-response/integrations/{integration_id}"

DEFAULT_TIMELINE_KAFKA_TOPICS = (
    "monitor.alerts",
    "governance.verdict.issued",
    "governance.enforcement.executed",
    "runtime.lifecycle",
    "auth.events",
    "policy.gate.blocked",
)

DEFAULT_ALERT_RULE_CLASS_TO_SCENARIO = {
    "error_rate_spike": "pod_failure",
    "sla_breach": "runtime_pod_crash_loop",
    "certification_failure": "certificate_expiry",
    "security_event": "auth_service_degradation",
    "chaos_unexpected_behavior": "governance_verdict_storm",
    "kafka_lag": "kafka_lag",
    "model_provider_outage": "model_provider_outage",
    "database_connection_issue": "database_connection_issue",
    "s3_quota_breach": "s3_quota_breach",
    "reasoning_engine_oom": "reasoning_engine_oom",
}
