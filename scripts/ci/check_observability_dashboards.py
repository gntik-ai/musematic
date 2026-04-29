#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = ROOT / "deploy/helm/observability/templates/dashboards"
LOKI_ALERTS = ROOT / "deploy/helm/observability/templates/alerts/loki-alerts.yaml"

D8_D21_DASHBOARDS = {
    "d8-control-plane-logs": "control-plane-logs.yaml",
    "d9-go-services-logs": "go-services-logs.yaml",
    "d10-frontend-web-logs": "frontend-web-logs.yaml",
    "d11-audit-event-stream": "audit-event-stream.yaml",
    "d12-cross-service-errors": "cross-service-errors.yaml",
    "d13-privacy-compliance": "privacy-compliance.yaml",
    "d14-security-compliance": "security-compliance.yaml",
    "cost-governance": "cost-governance.yaml",
    "multi-region-ops": "multi-region-ops.yaml",
    "d17-model-catalog": "model-catalog.yaml",
    "notifications-channels": "notifications-channels.yaml",
    "incident-response-runbooks": "incident-response.yaml",
    "d20-goal-lifecycle": "goal-lifecycle.yaml",
    "d21-governance-pipeline": "governance-pipeline.yaml",
}

BASELINE_DASHBOARDS = {
    "platform-overview": "platform-overview.yaml",
    "workflow-execution": "workflow-execution.yaml",
    "reasoning-engine": "reasoning-engine.yaml",
    "data-stores": "data-stores.yaml",
    "fleet-health": "fleet-health.yaml",
    "cost-intelligence": "cost-intelligence.yaml",
    "self-correction": "self-correction.yaml",
    "trust-content-moderation": "trust-content-moderation.yaml",
}

REQUIRED_ALERTS = {
    "HighErrorLogRate",
    "SecurityEventSpike",
    "DLPViolationSpike",
    "AuditChainAnomaly",
    "CostAnomalyLogged",
}


def main() -> int:
    errors: list[str] = []
    for uid, filename in {**D8_D21_DASHBOARDS, **BASELINE_DASHBOARDS}.items():
        try:
            dashboard = load_dashboard(filename)
        except Exception as exc:
            errors.append(f"{filename}: invalid dashboard JSON: {exc}")
            continue
        if dashboard.get("uid") != uid:
            errors.append(f"{filename}: uid {dashboard.get('uid')!r} != {uid!r}")
        if not dashboard.get("title"):
            errors.append(f"{filename}: missing title")
        if not isinstance(dashboard.get("panels"), list) or not dashboard["panels"]:
            errors.append(f"{filename}: missing panels")
        for index, panel in enumerate(dashboard.get("panels", []), start=1):
            if not isinstance(panel, dict):
                errors.append(f"{filename}: panel {index} is not an object")
                continue
            if not panel.get("title"):
                errors.append(f"{filename}: panel {index} missing title")
            if "targets" in panel and not isinstance(panel["targets"], list):
                errors.append(f"{filename}: panel {index} targets must be a list")

    alert_errors = validate_loki_alerts(LOKI_ALERTS.read_text(encoding="utf-8"))
    errors.extend(alert_errors)

    if errors:
        print("Observability dashboard validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        f"Validated {len(D8_D21_DASHBOARDS) + len(BASELINE_DASHBOARDS)} dashboard ConfigMaps "
        f"and {len(REQUIRED_ALERTS)} Loki alert rules."
    )
    return 0


def load_dashboard(filename: str) -> dict:
    text = (DASHBOARD_DIR / filename).read_text(encoding="utf-8")
    marker_index = text.index(": |\n") + len(": |\n")
    block = text[marker_index:]
    json_text = "\n".join(
        line[4:] if line.startswith("    ") else line
        for line in block.splitlines()
        if line.strip()
    )
    return json.loads(json_text)


def validate_loki_alerts(manifest: str) -> list[str]:
    errors: list[str] = []
    alert_names = set(re.findall(r"^\s*- alert:\s*([A-Za-z0-9_]+)\s*$", manifest, re.MULTILINE))
    missing = REQUIRED_ALERTS - alert_names
    if missing:
        errors.append(f"missing Loki alerts: {', '.join(sorted(missing))}")
    expressions = re.findall(r"^\s*expr:\s*(.+?)\s*$", manifest, re.MULTILINE)
    if len(expressions) < len(REQUIRED_ALERTS):
        errors.append(f"expected at least {len(REQUIRED_ALERTS)} LogQL expressions")
    for expr in expressions:
        if not _balanced(expr):
            errors.append(f"unbalanced LogQL expression: {expr}")
        if "{" not in expr or "}" not in expr:
            errors.append(f"LogQL expression missing selector: {expr}")
        if not re.search(r"\[[0-9]+[smhd]\]", expr):
            errors.append(f"LogQL expression missing range vector: {expr}")
    if "incident_trigger: audit_chain_anomaly" not in manifest:
        errors.append("AuditChainAnomaly must carry incident_trigger label")
    return errors


def _balanced(value: str) -> bool:
    stack: list[str] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    in_quote = False
    escaped = False
    for char in value:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_quote = not in_quote
            continue
        if in_quote:
            continue
        if char in "([{":
            stack.append(char)
        elif char in ")]}":
            if not stack or stack.pop() != pairs[char]:
                return False
    return not stack and not in_quote


if __name__ == "__main__":
    raise SystemExit(main())
