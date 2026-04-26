# Planning Input — Incident Response and Runbooks

> Verbatim brownfield input that motivated this spec. Preserved here as a
> planning artifact. The implementation strategy (specific tables,
> services, schemas, code-level integration points) is intentionally
> deferred to the planning phase. This file is a planning input, not a
> contract.

## Brownfield Context
**Modifies:** `analytics/`, operator dashboard, documentation structure
**FRs:** FR-505, FR-506, FR-507

## Summary
Integrate with PagerDuty/OpsGenie/VictorOps, provide inline runbooks for common incidents, publish post-mortem templates with timeline reconstruction from audit log + execution journal + Kafka events.

## Database Changes (planning input — not a contract)
```sql
CREATE TABLE incident_integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider VARCHAR(32) NOT NULL, -- pagerduty, opsgenie, victorops
    integration_key_ref VARCHAR(256) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    alert_severity_mapping JSONB
);

CREATE TABLE incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id VARCHAR(256),
    severity VARCHAR(16) NOT NULL,
    title VARCHAR(512) NOT NULL,
    description TEXT,
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    related_executions JSONB,
    related_events JSONB,
    post_mortem_id UUID
);

CREATE TABLE runbooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scenario VARCHAR(256) NOT NULL UNIQUE,
    symptoms TEXT,
    diagnostic_commands JSONB,
    remediation_steps TEXT,
    escalation_path TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE post_mortems (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id),
    timeline JSONB NOT NULL,
    impact_assessment TEXT,
    root_cause TEXT,
    action_items JSONB,
    distribution_list JSONB,
    blameless BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## New Files
- `incident_response/` bounded context (or extend `analytics/`)
- `incident_response/services/incident_service.py`
- `incident_response/services/integration_service.py` — PagerDuty/OpsGenie/VictorOps clients
- `incident_response/services/runbook_service.py`
- `incident_response/services/post_mortem_service.py` — timeline reconstruction from audit log + journal + Kafka
- Seed 10 initial runbooks: pod failure, database connection issue, Kafka lag, model provider outage, certificate expiry, S3 quota breach, governance verdict storm, auth service degradation, reasoning engine OOM, runtime pod crash loop

## Modified Files
- `analytics/services/alert_rules.py` — trigger incident creation on rule match
- Operator dashboard — add Incidents tab with runbook links

## Acceptance Criteria
- [ ] PagerDuty/OpsGenie/VictorOps integration configurable
- [ ] Alert rules trigger incidents automatically
- [ ] 10 runbooks seeded and accessible from operator dashboard
- [ ] Post-mortem template generates timeline from audit + journal + events
- [ ] Post-mortems linkable to executions and certifications
