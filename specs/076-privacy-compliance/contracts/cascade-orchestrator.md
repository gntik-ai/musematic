# Cascade Orchestrator Contract

**Feature**: 076-privacy-compliance
**Module**: `apps/control-plane/src/platform/privacy_compliance/services/cascade_orchestrator.py`
**Adapters**: `apps/control-plane/src/platform/privacy_compliance/cascade_adapters/`

## Cascade adapter interface

```python
# cascade_adapters/base.py
class CascadeAdapter(ABC):
    store_name: ClassVar[str]  # "postgresql", "qdrant", "opensearch", "s3", "clickhouse", "neo4j"

    @abstractmethod
    async def dry_run(self, subject_user_id: UUID) -> CascadePlan:
        """Return what would be deleted without deleting anything."""

    @abstractmethod
    async def execute(self, subject_user_id: UUID) -> CascadeResult:
        """Perform deletion. Idempotent on retry."""

@dataclass
class CascadePlan:
    store_name: str
    estimated_count: int
    per_target_estimates: dict[str, int]  # table/collection/index/bucket → count

@dataclass
class CascadeResult:
    store_name: str
    started_at: datetime
    completed_at: datetime
    affected_count: int
    per_target_counts: dict[str, int]
    errors: list[str]  # empty on success
```

## Orchestrator

```python
class CascadeOrchestrator:
    def __init__(self, adapters: list[CascadeAdapter], audit_chain, signer, salt_provider):
        self._adapters = sorted(adapters, key=lambda a: STORE_ORDER.index(a.store_name))
        # STORE_ORDER = ["postgresql", "qdrant", "opensearch", "s3", "clickhouse", "neo4j"]

    async def run(
        self,
        dsr_id: UUID,
        subject_user_id: UUID,
        *,
        dry_run: bool = False,
    ) -> Tombstone | CascadePlan:
        cascade_log = []
        entities_deleted = {}
        all_errors = []

        for adapter in self._adapters:
            try:
                result = await (adapter.dry_run(subject_user_id) if dry_run
                                else adapter.execute(subject_user_id))
                cascade_log.append({
                    "store_name": adapter.store_name,
                    "status": "success" if not result.errors else "partial",
                    "started_at_iso": result.started_at.isoformat(),
                    "completed_at_iso": result.completed_at.isoformat(),
                    "affected_count": result.affected_count,
                    "per_target_counts": result.per_target_counts,
                    "errors": result.errors,
                })
                entities_deleted[adapter.store_name] = result.affected_count
                if result.errors:
                    all_errors.extend(result.errors)
            except Exception as e:
                cascade_log.append({
                    "store_name": adapter.store_name,
                    "status": "failed",
                    "error": str(e),
                })
                all_errors.append(f"{adapter.store_name}: {e}")

        if dry_run:
            return CascadePlan(...)

        tombstone = await self._produce_tombstone(
            subject_user_id, entities_deleted, cascade_log
        )

        if all_errors:
            raise CascadePartialFailure(tombstone, all_errors)
        return tombstone
```

## Tombstone construction

```python
async def _produce_tombstone(self, subject_user_id, entities_deleted, cascade_log):
    salt = await self._salt_provider.get_current_salt()
    subject_hash = sha256(subject_user_id.bytes + salt).hexdigest()

    canonical_payload = {
        "subject_user_id_hash": subject_hash,
        "salt_version": await self._salt_provider.get_current_version(),
        "entities_deleted": dict(sorted(entities_deleted.items())),
        "cascade_log": sorted(cascade_log, key=lambda e: e["started_at_iso"]),
        "created_at_iso": datetime.now(UTC).isoformat(),
    }
    canonical_json = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"))
    proof_hash = sha256(canonical_json.encode()).hexdigest()

    tombstone = await self._repo.insert_tombstone(
        subject_user_id_hash=subject_hash,
        salt_version=canonical_payload["salt_version"],
        entities_deleted=canonical_payload["entities_deleted"],
        cascade_log=canonical_payload["cascade_log"],
        proof_hash=proof_hash,
    )
    await self._audit_chain.append(
        audit_event_id=tombstone.id,
        audit_event_source="privacy_compliance",
        canonical_payload=canonical_json.encode(),
    )
    return tombstone
```

## Signed tombstone export

```python
async def export_signed(self, tombstone_id: UUID) -> SignedTombstone:
    tombstone = await self._repo.get_tombstone(tombstone_id)
    canonical_json = _recompute_canonical(tombstone)  # deterministic re-construction
    assert sha256(canonical_json.encode()).hexdigest() == tombstone.proof_hash, "integrity check"
    signature = await self._signer.sign(canonical_json.encode())  # UPD-024's Ed25519 key
    return SignedTombstone(
        tombstone=canonical_json,
        key_version=await self._signer.current_key_version(),
        signature=base64.b64encode(signature).decode(),
    )
```

## Per-adapter semantics

### PostgreSQL adapter (`postgresql_adapter.py`)

Per-table column map:

```python
USER_IDENTITY_COLUMNS: dict[str, list[str]] = {
    "users": ["id"],                # root — must delete last
    "user_credentials": ["user_id"],
    "mfa_enrollments": ["user_id"],
    "oauth_audit_entries": ["user_id"],
    "oauth_links": ["user_id"],
    "user_roles": ["user_id"],
    "auth_attempts": ["user_id"],
    "accounts_users": ["user_id", "suspended_by", "blocked_by", "archived_by"],
    "invitations": ["user_id", "inviter_id", "consumed_by_user_id", "revoked_by"],
    "approval_requests": ["user_id", "reviewer_id"],
    "workspaces_workspaces": ["owner_id"],
    "workspaces_memberships": ["user_id"],
    "workspaces_goals": ["created_by"],
    "interactions_conversations": ["created_by"],
    "interactions_interactions": ["participant_user_id"],
    "execution_executions": ["created_by"],
    "execution_reprioritization_triggers": ["created_by"],
    "evaluation_eval_sets": ["created_by"],
    "evaluation_rubrics": ["created_by"],
    "evaluation_calibration_runs": ["created_by"],
    "evaluation_ate_configs": ["created_by"],
    "evaluation_human_ai_grades": ["reviewer_id"],
    "registry_namespaces": ["created_by"],
    "registry_agent_profiles": ["created_by"],
    "policies_policy_versions": ["created_by"],
    "policies_attachments": ["created_by"],
    "mcp_server_registrations": ["created_by"],
    "mcp_exposed_tools": ["created_by"],
    "memory_knowledge_nodes": ["created_by"],
    "composition_requests": ["requested_by"],
    "fleet_learning_cross_fleet_transfers": ["approved_by"],
    "agentops_cicd_gate_results": ["requested_by"],
    "agentops_adaptation_proposals": ["revoked_by"],
    "marketplace_ratings": ["user_id"],
    "marketplace_recommendations": ["user_id"],
    "notifications_user_alerts": ["user_id"],
    "notifications_alert_settings": ["user_id"],
    "a2a_external_endpoints": ["created_by"],
    # 38 tables total — add new PII-bearing tables as they are introduced
}
```

Deletion order: bottom-up — child tables before parent. `users` row
deleted last (FK constraints let most cascade via `ON DELETE` where
defined; explicit DELETEs fill gaps).

For non-PK columns (e.g. `created_by` on `registry_agent_profiles`),
the column is NULLified (set to a sentinel `DELETED_SUBJECT_UUID`
constant) rather than the row deleted — the row is not the subject's,
only its authorship is.

### Qdrant adapter

```python
await qdrant_client.delete(
    collection_name="*",
    points_selector=models.Filter(
        must=[models.FieldCondition(
            key="user_id",
            match=models.MatchValue(value=str(subject_user_id))
        )]
    ),
)
```

### OpenSearch adapter

```python
await opensearch_client.delete_by_query(
    index="*",
    body={"query": {"term": {"user_id": str(subject_user_id)}}},
)
```

### S3 adapter

New helper `common/clients/object_storage.py::delete_objects_matching_prefix`:

```python
async def delete_objects_matching_prefix(bucket: str, prefix: str) -> int:
    count = 0
    async for page in self._list_objects_v2(bucket, prefix=prefix, paginate=True):
        batch = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
        if batch:
            await self._client.delete_objects(Bucket=bucket, Delete={"Objects": batch})
            count += len(batch)
    return count
```

Called for every configured bucket with `prefix=f"users/{subject_user_id}/"`.

### ClickHouse adapter

```python
for table in CLICKHOUSE_PII_TABLES:
    await ch_client.execute_command(
        f"ALTER TABLE {table} UPDATE is_deleted = 1 WHERE user_id = %(uid)s",
        {"uid": str(subject_user_id)},
    )
```

The monthly compactor (follow-up feature) hard-deletes tombstoned rows.

### Neo4j adapter (PostgreSQL-fallback today)

```python
await pg.execute(text("""
    DELETE FROM graph_edges WHERE source_node_id IN (
        SELECT id FROM graph_nodes WHERE owner_user_id = :uid
    ) OR target_node_id IN (
        SELECT id FROM graph_nodes WHERE owner_user_id = :uid
    );
    DELETE FROM graph_nodes WHERE owner_user_id = :uid;
"""), {"uid": str(subject_user_id)})
```

## Unit-test contract

- **CO1** — orchestrator runs all 6 adapters in order; tombstone produced.
- **CO2** — dry_run does not mutate any store; returns estimated counts.
- **CO3** — partial failure: Qdrant raises → tombstone still produced;
  cascade_log entries for each store; DSR → `failed` with errors.
- **CO4** — retry after failure: successful stores skipped; failing
  store re-attempted; idempotent.
- **CO5** — `users` row deleted last (PG adapter order).
- **CO6** — tombstone `proof_hash` matches SHA-256 of canonical payload.
- **CO7** — `subject_user_id_hash` uses current salt; never contains
  raw UUID.
- **CO8** — signed tombstone verifies with UPD-024's public key on an
  external client.
- **CO9** — coverage CI check: declared `USER_IDENTITY_COLUMNS` matches
  grep of `ForeignKey("users.id")` across platform/ modules.
