# musematic Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-26

## Active Technologies
- Python 3.12+ (control plane). No Go changes. (079-cost-governance-chargeback)
- PostgreSQL — 5 new tables (`cost_attributions`, `workspace_budgets`, `budget_alerts`, `cost_forecasts`, `cost_anomalies`) via Alembic migration `062_cost_governance.py`. ClickHouse — 1 new table `cost_events` added to `cost_governance/clickhouse_setup.py` following the `analytics/clickhouse_setup.py` pattern (`CREATE TABLE IF NOT EXISTS`, monthly partition, TTL ≥ 2 years to satisfy spec assumption "at least one full annual finance cycle"). Redis — 2 new key patterns: `cost:budget:{workspace_id}:{period_type}:{period_start}` (period spend hot counter, TTL = period length + 1d) and `cost:override:{workspace_id}:{nonce}` (single-shot admin override token, TTL ≤ 5 min). No Vault paths. (079-cost-governance-chargeback)
- PostgreSQL — 4 new tables (`incident_integrations`, `incidents`, `runbooks`, `post_mortems`) via Alembic migration `063_incident_response.py`, plus a fifth supporting table `incident_external_alerts` for the per-(incident, integration) external-reference + delivery-state tracking that the brownfield JSONB sketch would otherwise hide. Redis — 2 new key patterns: `incident:dedup:{condition_fingerprint}` (open-incident lookup, TTL = max-incident-age + grace; FR-505.5) and `incident:delivery:{integration_id}:{external_alert_id}` (retry-state cache, TTL = retry envelope; FR-505.6). MinIO — 1 reserved bucket prefix `incident-response-postmortems` for post-mortem timeline blobs that exceed the PostgreSQL row-size budget; a row points at the blob. No Vault paths owned by this BC — provider credentials are stored at `secret/data/incident-response/integrations/{integration_id}` via the existing `SecretProvider` (`common/clients/model_router.py:43–44`; `RotatableSecretProvider.get_current()` at `security_compliance/providers/rotatable_secret_provider.py:21`). (080-incident-response-runbooks)

- Go 1.25.x for `services/reasoning-engine`; Python 3.12+ for `apps/control-plane` + gRPC + protobuf, pgx/v5, Redis, Kafka, custom Go persistence helpers, FastAPI, SQLAlchemy 2.x async, Pydantic v2, aioboto3 (056-ibor-integration-and)

## Project Structure

```text
src/
tests/
```

## Commands

cd src && pytest && ruff check .

## Code Style

Go 1.25.x for `services/reasoning-engine`; Python 3.12+ for `apps/control-plane`: Follow standard conventions

## Recent Changes
- 080-incident-response-runbooks: Added Python 3.12+ (control plane). No Go changes. `IncidentTriggerInterface` is the single in-process producer contract for incident creation; do not add parallel alert-ingestion paths. `analytics/services/alert_rules.py` does not exist; the canonical analytics hook lives in `analytics/service.py`.
- 079-cost-governance-chargeback: Added Python 3.12+ (control plane). No Go changes. Cost analytics follow the analytics-delegation migration path via `cost_governance/clickhouse_setup.py`; do not reintroduce a parallel cost path.

- 056-ibor-integration-and: Added Go 1.25.x for `services/reasoning-engine`; Python 3.12+ for `apps/control-plane` + gRPC + protobuf, pgx/v5, Redis, Kafka, custom Go persistence helpers, FastAPI, SQLAlchemy 2.x async, Pydantic v2, aioboto3

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
