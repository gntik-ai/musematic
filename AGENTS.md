# musematic Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-27

## Active Technologies
- Python 3.12+ (control plane). No Go changes. (079-cost-governance-chargeback)
- PostgreSQL — 5 new tables (`cost_attributions`, `workspace_budgets`, `budget_alerts`, `cost_forecasts`, `cost_anomalies`) via Alembic migration `062_cost_governance.py`. ClickHouse — 1 new table `cost_events` added to `cost_governance/clickhouse_setup.py` following the `analytics/clickhouse_setup.py` pattern (`CREATE TABLE IF NOT EXISTS`, monthly partition, TTL ≥ 2 years to satisfy spec assumption "at least one full annual finance cycle"). Redis — 2 new key patterns: `cost:budget:{workspace_id}:{period_type}:{period_start}` (period spend hot counter, TTL = period length + 1d) and `cost:override:{workspace_id}:{nonce}` (single-shot admin override token, TTL ≤ 5 min). No Vault paths. (079-cost-governance-chargeback)
- PostgreSQL — 4 new tables (`incident_integrations`, `incidents`, `runbooks`, `post_mortems`) via Alembic migration `063_incident_response.py`, plus a fifth supporting table `incident_external_alerts` for the per-(incident, integration) external-reference + delivery-state tracking that the brownfield JSONB sketch would otherwise hide. Redis — 2 new key patterns: `incident:dedup:{condition_fingerprint}` (open-incident lookup, TTL = max-incident-age + grace; FR-505.5) and `incident:delivery:{integration_id}:{external_alert_id}` (retry-state cache, TTL = retry envelope; FR-505.6). MinIO — 1 reserved bucket prefix `incident-response-postmortems` for post-mortem timeline blobs that exceed the PostgreSQL row-size budget; a row points at the blob. No Vault paths owned by this BC — provider credentials are stored at `secret/data/incident-response/integrations/{integration_id}` via the existing `SecretProvider` (`common/clients/model_router.py:43–44`; `RotatableSecretProvider.get_current()` at `security_compliance/providers/rotatable_secret_provider.py:21`). (080-incident-response-runbooks)
- YAML (Helm chart values + dashboard ConfigMaps + alert rules) + Python 3.12+ (control plane structlog config + audit-chain log-emission additive change) + Go 1.22+ (Go satellite ContextHandler) + TypeScript 5.x (frontend isomorphic logger). No SQL changes (this feature owns no relational tables). (084-log-aggregation-dashboards)
- S3-compatible object storage for Loki chunk storage via the existing generic-S3 client (`S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_USE_PATH_STYLE` env vars per Principle XVI). Bucket name: `platform-loki-chunks` (constitutionally reserved). One in-cluster persistent volume claim (20 GiB default; configurable per Helm values) for Loki's hot tier write path. No PostgreSQL / Redis / Qdrant / Neo4j changes. **OTEL Collector is unchanged** — its existing metrics-→-Prometheus and traces-→-Jaeger pipelines from feature 047 stay; logs do NOT route through the collector (they go via Promtail directly). (084-log-aggregation-dashboards)
- Markdown + Python 3.12 stdlib + YAML only: root README, shared SVG asset, README parity checker, GitHub Actions wiring, weekly external-link workflow. No app code, migrations, data stores, or runtime deps. (088-multilingual-repository-readme)

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
- 088-multilingual-repository-readme: Added canonical English README, shared architecture SVG, README parity checker/tests, CI readme path filter, drift issue helper, weekly external-link workflow, and operator quickstart. Vendor translations/native reviews remain external gates.
- 084-log-aggregation-dashboards: Added YAML (Helm chart values + dashboard ConfigMaps + alert rules) + Python 3.12+ (control plane structlog config + audit-chain log-emission additive change) + Go 1.22+ (Go satellite ContextHandler) + TypeScript 5.x (frontend isomorphic logger). No SQL changes (this feature owns no relational tables).
- 080-incident-response-runbooks: Added Python 3.12+ (control plane). No Go changes. `IncidentTriggerInterface` is the single in-process producer contract for incident creation; do not add parallel alert-ingestion paths. `analytics/services/alert_rules.py` does not exist; the canonical analytics hook lives in `analytics/service.py`.
- 079-cost-governance-chargeback: Added Python 3.12+ (control plane). No Go changes. Cost analytics follow the analytics-delegation migration path via `cost_governance/clickhouse_setup.py`; do not reintroduce a parallel cost path.


<!-- MANUAL ADDITIONS START -->
UPD-038 corrections: six README files total; root `LICENSE`/`CONTRIBUTING.md`/`SECURITY.md` absent and out of scope; docs links match today's `docs/` tree; `docs/assets/` is created here; `make dev-up` is verified; GitHub repo is `gntik-ai/musematic`; `ci.yml` owns the per-PR README filter; `gh` uses `GITHUB_TOKEN`/`GH_TOKEN`; CI installs `pandoc`; cold-cache quick start can exceed 5 minutes; feature 083 vendor reuse is unconfirmed; native-speaker reviews are an external gate.
<!-- MANUAL ADDITIONS END -->
