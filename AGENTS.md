# musematic Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-26

## Active Technologies
- Python 3.12+ (control plane). No Go changes. (079-cost-governance-chargeback)
- PostgreSQL — 5 new tables (`cost_attributions`, `workspace_budgets`, `budget_alerts`, `cost_forecasts`, `cost_anomalies`) via Alembic migration `062_cost_governance.py`. ClickHouse — 1 new table `cost_events` added to `cost_governance/clickhouse_setup.py` following the `analytics/clickhouse_setup.py` pattern (`CREATE TABLE IF NOT EXISTS`, monthly partition, TTL ≥ 2 years to satisfy spec assumption "at least one full annual finance cycle"). Redis — 2 new key patterns: `cost:budget:{workspace_id}:{period_type}:{period_start}` (period spend hot counter, TTL = period length + 1d) and `cost:override:{workspace_id}:{nonce}` (single-shot admin override token, TTL ≤ 5 min). No Vault paths. (079-cost-governance-chargeback)

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
- 079-cost-governance-chargeback: Added Python 3.12+ (control plane). No Go changes. Cost analytics follow the analytics-delegation migration path via `cost_governance/clickhouse_setup.py`; do not reintroduce a parallel cost path.

- 056-ibor-integration-and: Added Go 1.25.x for `services/reasoning-engine`; Python 3.12+ for `apps/control-plane` + gRPC + protobuf, pgx/v5, Redis, Kafka, custom Go persistence helpers, FastAPI, SQLAlchemy 2.x async, Pydantic v2, aioboto3

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
