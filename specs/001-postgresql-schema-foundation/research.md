# Research: PostgreSQL Deployment and Schema Foundation

**Feature**: 001-postgresql-schema-foundation  
**Date**: 2026-04-09  
**Status**: Complete — all unknowns resolved

---

## Decision 1: CloudNativePG Pooler CRD vs Standalone PgBouncer

**Decision**: Use the **CloudNativePG Pooler CRD** instead of a standalone PgBouncer Deployment.

**Rationale**: CNPG's built-in Pooler CRD manages the full lifecycle — it automatically discovers the primary endpoint after failover, syncs credentials from the cluster Secret, rotates TLS certificates, and creates a PodMonitor for Prometheus without additional configuration. This reduces Helm chart complexity by eliminating manual ConfigMap, userlist generation (init containers), and exporter sidecars.

**Alternatives considered**:
- Standalone PgBouncer Deployment with exporter sidecar — more operational flexibility for multi-cluster scenarios, but unnecessary for this single-cluster setup. Adds credential management complexity (MD5 hash generation in init containers).
- Session-mode pooling — rejected because transaction-mode is correct for async SQLAlchemy, which does not hold connections between requests.

**CNPG Pooler CRD reference**:
```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Pooler
metadata:
  name: musematic-pooler
  namespace: platform-data
spec:
  cluster:
    name: musematic-postgres
  instances: 2
  pgbouncer:
    poolMode: transaction
    maxClientConn: 1000
    defaultPoolSize: 10
    maxDbConnections: 200
```

---

## Decision 2: Synchronous Replica Configuration

**Decision**: Use `synchronous_commit: "on"` + `synchronous_standby_names: "*"` PostgreSQL parameters inside the Cluster CRD. CNPG manages replication slots automatically.

**Rationale**: CNPG handles replication slot creation internally. The `synchronous_standby_names: "*"` setting requires all replicas to acknowledge writes before the primary confirms a commit — providing the strongest consistency guarantee. There is no field called `synchronizeReplicasFromNodeLabels` in the standard CRD.

**Alternatives considered**:
- `synchronous_standby_names: "ANY 1 (*)"` — quorum-based, faster under single replica failure but weaker consistency guarantee. Rejected to match the spec's requirement for synchronous HA.

---

## Decision 3: PodDisruptionBudget

**Decision**: Deploy PDB as a **separate Kubernetes resource** alongside the CNPG Cluster CRD, since CNPG does not create PDBs automatically.

**Rationale**: CNPG auto-labels all cluster pods with `cnpg.io/cluster: <cluster-name>` and `role: instance`. A PDB using these selectors with `maxUnavailable: 1` correctly constrains voluntary disruptions for the 3-node cluster.

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: musematic-postgres-pdb
  namespace: platform-data
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      cnpg.io/cluster: musematic-postgres
      role: instance
```

---

## Decision 4: Alembic Async Migration Pattern

**Decision**: Use `create_async_engine` with `connection.run_sync(do_run_migrations)` inside `async with connectable.begin()`. Call `asyncio.run(run_migrations_online())` at module level.

**Rationale**: Alembic's migration context is synchronous. The `run_sync` bridge allows async SQLAlchemy to drive Alembic's synchronous migration execution. Using `pool.NullPool` in the engine prevents connection leaks during migration runs.

**Key env.py skeleton**:
```python
async def run_migrations_online() -> None:
    connectable = create_async_engine(DATABASE_URL, poolclass=pool.NullPool)
    async with connectable.begin() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

asyncio.run(run_migrations_online())
```

**DATABASE_URL format**: `postgresql+asyncpg://user:password@host:port/dbname`

---

## Decision 5: SQLAlchemy 2.x Mixin Style

**Decision**: Use `Mapped[Type]` with `mapped_column()` (SQLAlchemy 2.x declarative style). Do not use the 1.x `Column()` pattern.

**Key patterns per mixin**:

| Mixin | Key mechanism |
|-------|--------------|
| `UUIDMixin` | `mapped_column(PG_UUID, primary_key=True, server_default=func.gen_random_uuid())` |
| `TimestampMixin` | `server_default=func.now()` for `created_at`; `onupdate` for `updated_at` |
| `SoftDeleteMixin` | `@hybrid_property` for Python check + `@is_deleted.expression` for SQL filter |
| `EventSourcedMixin` | `__mapper_args__ = {"version_id_col": version}` — triggers `StaleDataError` automatically |
| `WorkspaceScopedMixin` | FK to `workspaces.id` with `index=True` |
| `AuditMixin` | Two FKs to `users.id` (`created_by`, `updated_by`) |

**Optimistic locking**: SQLAlchemy's built-in `version_id_col` increments `version` on every UPDATE. If a session tries to commit with a stale version, `StaleDataError` is raised before the UPDATE executes.

---

## Decision 6: Append-Only Enforcement

**Decision**: Use PostgreSQL `CREATE RULE` statements to block `UPDATE` and `DELETE` on audit and execution event tables, implemented directly in the Alembic migration.

**Rationale**: Rules fire at the SQL level before any ORM or application code, making them impossible to bypass accidentally. Triggers could also work but rules are simpler for the "do nothing" case.

```sql
CREATE RULE audit_no_update AS ON UPDATE TO audit_events DO INSTEAD NOTHING;
CREATE RULE audit_no_delete AS ON DELETE TO audit_events DO INSTEAD NOTHING;
```

---

## Decision 7: Agent Namespace FQN Uniqueness

**Decision**: Enforce `name UNIQUE` on `agent_namespaces`. Enforce `(namespace_id, local_name) UNIQUE` on `agent_profiles` (created in a future migration). The FQN string `namespace:local_name` is derived at read time; no denormalized FQN column is stored.

**Rationale**: Storing the FQN as a derived value avoids update anomalies. Uniqueness via a composite unique constraint on `(namespace_id, local_name)` plus the unique constraint on `agent_namespaces.name` guarantees platform-wide FQN uniqueness.

---

## Resolved Unknowns Summary

| Unknown | Resolution |
|---------|-----------|
| PgBouncer deployment style | CNPG Pooler CRD |
| Synchronous replica config | `synchronous_standby_names: "*"` parameter |
| PDB automatic vs manual | Manual separate resource |
| Alembic async driver | `asyncpg` + `run_sync` bridge |
| SQLAlchemy version syntax | 2.x `Mapped[]` / `mapped_column()` |
| Append-only enforcement | PostgreSQL `CREATE RULE` in migrations |
| FQN storage | Derived (not stored); uniqueness via composite constraint |
