from __future__ import annotations

from platform.incident_response.seeds.runbooks_v1 import (
    RUNBOOK_SCENARIOS,
    RUNBOOKS_V1,
    seed_initial_runbooks,
)
from typing import Any

from sqlalchemy.dialects import postgresql

EXPECTED_SCENARIOS = {
    "pod_failure",
    "database_connection_issue",
    "kafka_lag",
    "model_provider_outage",
    "certificate_expiry",
    "s3_quota_breach",
    "governance_verdict_storm",
    "auth_service_degradation",
    "reasoning_engine_oom",
    "runtime_pod_crash_loop",
}


def test_seeded_runbooks_include_exact_initial_scenarios_with_required_fields() -> None:
    assert set(RUNBOOK_SCENARIOS) == EXPECTED_SCENARIOS
    assert {item["scenario"] for item in RUNBOOKS_V1} == EXPECTED_SCENARIOS
    for item in RUNBOOKS_V1:
        assert item["symptoms"]
        assert item["diagnostic_commands"]
        assert item["remediation_steps"]
        assert item["escalation_path"]


def test_seeded_runbook_insert_is_idempotent() -> None:
    class Connection:
        def __init__(self) -> None:
            self.statements: list[Any] = []

        def execute(self, statement: Any) -> None:
            self.statements.append(statement)

    connection = Connection()
    seed_initial_runbooks(connection)
    seed_initial_runbooks(connection)

    compiled = str(connection.statements[0].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT" in compiled
    assert len(connection.statements) == 2
