# Quickstart: PostgreSQL Deployment and Schema Foundation

**Feature**: 001-postgresql-schema-foundation  
**Date**: 2026-04-09

---

## Prerequisites

- Kubernetes cluster with CloudNativePG operator installed (`helm install cnpg cloudnative-pg/cloudnative-pg`)
- `kubectl` configured for target cluster
- `helm` 3.x
- Python 3.11+ with `uv` or `pip`
- PostgreSQL client (`psql`) for verification

Install the control-plane package before running migrations or tests:

```bash
pip install -e ./apps/control-plane
```

---

## 1. Deploy PostgreSQL Cluster (Production)

```bash
# Install the Helm chart for production
helm install musematic-postgres deploy/helm/postgresql \
  --namespace platform-data \
  --create-namespace \
  --set environment=production \
  --set storage.storageClass=your-storage-class \
  --set storage.size=100Gi

# Verify cluster is ready (3 pods)
kubectl get clusters -n platform-data
kubectl get pods -n platform-data -l cnpg.io/cluster=musematic-postgres

# Verify primary is elected
kubectl get cluster musematic-postgres -n platform-data \
  -o jsonpath='{.status.currentPrimary}'
```

---

## 2. Deploy PostgreSQL Cluster (Development)

```bash
helm install musematic-postgres deploy/helm/postgresql \
  --namespace platform-data \
  --create-namespace \
  --set environment=development

# Single pod, no PgBouncer
kubectl get pods -n platform-data
```

---

## 3. Run Database Migrations

```bash
# Export connection string (use direct PG connection for migrations)
export DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/musematic"
export PSQL_URL="postgresql://postgres:password@localhost:5432/musematic"

# Forward the primary service port locally
kubectl port-forward svc/musematic-postgres-rw 5432:5432 -n platform-data &

# Apply all migrations
make migrate

# Verify schema
psql "$PSQL_URL" -c "\dt"
```

---

## 4. Roll Back Last Migration

```bash
make migrate-rollback
```

---

## 5. Verify Connection Pooling (Production)

```bash
# Connect through PgBouncer (transaction mode)
kubectl port-forward svc/musematic-pooler 5432:5432 -n platform-data &
psql "postgresql://postgres:password@localhost:5432/musematic" \
  -c "SELECT current_user, inet_server_addr();"

# Check PgBouncer pool stats
psql "postgresql://postgres:password@localhost:5432/pgbouncer" \
  -c "SHOW POOLS;"
```

---

## 6. Verify Prometheus Metrics

```bash
# pg_exporter metrics (auto-enabled on CNPG cluster)
kubectl port-forward pod/musematic-postgres-1 9187:9187 -n platform-data &
curl http://localhost:9187/metrics | grep pg_up

# PgBouncer metrics (via CNPG Pooler built-in PodMonitor)
kubectl get podmonitor -n platform-data
```

---

## 7. Test Automatic Failover

```bash
# Delete the primary pod and watch failover
kubectl delete pod musematic-postgres-1 -n platform-data

# Watch cluster status (should elect new primary within 30s)
kubectl get cluster musematic-postgres -n platform-data -w
```

---

## 8. Using SQLAlchemy Models in Application Code

```python
from platform.common.database import get_async_session
from sqlalchemy import select
from platform.common.models import User, Workspace

# Create a new user
async with get_async_session() as session:
    user = User(
        email="alice@example.com",
        display_name="Alice",
        created_by=admin_id,
        updated_by=admin_id,
    )
    session.add(user)
    await session.commit()

# Query excluding soft-deleted records (default behavior)
async with get_async_session() as session:
    stmt = select(User).where(~User.is_deleted)
    result = await session.execute(stmt)
    active_users = result.scalars().all()
```

---

## 9. Create a New Migration

```bash
# Generate a new migration file
make migrate-create NAME=add_agent_profiles

# Edit the generated file in apps/control-plane/migrations/versions/
# Then apply it
make migrate
```

---

## Makefile Reference

| Target | Description |
|--------|-------------|
| `make migrate` | `alembic upgrade head` |
| `make migrate-rollback` | `alembic downgrade -1` |
| `make migrate-create NAME=...` | `alembic revision --autogenerate -m <NAME>` |
| `make migrate-check` | Verify no branch conflicts in migration chain |
| `python -m pytest apps/control-plane/tests` | Run migration and model tests |
