# Quickstart: Agent Registry and Ingest

**Feature**: 021-agent-registry-ingest  
**Date**: 2026-04-11

---

## Prerequisites

- PostgreSQL running with migration `006_registry_tables` applied
- OpenSearch running (marketplace-agents index created at startup)
- Qdrant running (agent_embeddings collection created at startup)
- MinIO running with `agent-packages` bucket
- Kafka running with `registry.events` topic
- Control plane API started (`api` profile)

---

## Setup

### 1. Apply the Alembic migration

```bash
cd apps/control-plane
make migrate
# Applies 006_registry_tables.py — creates 5 registry tables
```

### 2. Verify indices created at startup

```bash
# Check OpenSearch index
curl http://localhost:9200/marketplace-agents

# Check Qdrant collection
curl http://localhost:6333/collections/agent_embeddings

# Should see index/collection details without error
```

---

## Sample Workflows

### Create a namespace

```bash
curl -X POST http://localhost:8000/api/v1/namespaces \
  -H "Authorization: Bearer $JWT" \
  -H "X-Workspace-ID: $WORKSPACE_ID" \
  -H "Content-Type: application/json" \
  -d '{"name": "finance-ops", "description": "Financial operations agents"}'

# Expect 201 with namespace record
```

### Upload an agent package

```bash
# First create a test package
mkdir -p /tmp/kyc-agent
cat > /tmp/kyc-agent/manifest.yaml << 'EOF'
local_name: kyc-verifier
version: 1.0.0
purpose: >
  Verifies Know Your Customer documents for regulatory compliance by
  extracting fields, checking against PEP/sanction lists, and emitting
  a structured compliance verdict.
approach: >
  1. Accept document bytes as input.
  2. Extract structured fields using document parser tool.
  3. Query compliance rules database.
  4. Cross-reference against PEP and sanctions lists.
  5. Return pass/fail verdict with evidence trail.
role_types: [executor]
maturity_level: 0
tags: [kyc, compliance, finance]
EOF
cat > /tmp/kyc-agent/agent.py << 'EOF'
# Main agent implementation placeholder
EOF
cd /tmp && tar -czf kyc-verifier-1.0.0.tar.gz kyc-agent/

# Upload
curl -X POST http://localhost:8000/api/v1/agents/upload \
  -H "Authorization: Bearer $JWT" \
  -H "X-Workspace-ID: $WORKSPACE_ID" \
  -F "namespace_name=finance-ops" \
  -F "package=@/tmp/kyc-verifier-1.0.0.tar.gz"

# Expect 201 with agent_profile.status="draft" and created=true
```

### Resolve FQN

```bash
curl http://localhost:8000/api/v1/agents/resolve/finance-ops:kyc-verifier \
  -H "Authorization: Bearer $JWT" \
  -H "X-Workspace-ID: $WORKSPACE_ID"

# Expect 200 within 200ms, full agent profile
```

### Transition lifecycle

```bash
AGENT_ID="<id from upload response>"

# draft → validated
curl -X POST http://localhost:8000/api/v1/agents/$AGENT_ID/transition \
  -H "Authorization: Bearer $JWT" \
  -H "X-Workspace-ID: $WORKSPACE_ID" \
  -H "Content-Type: application/json" \
  -d '{"target_status": "validated", "reason": "Structure check passed"}'

# validated → published (emits registry.agent.published event)
curl -X POST http://localhost:8000/api/v1/agents/$AGENT_ID/transition \
  -H "Authorization: Bearer $JWT" \
  -H "X-Workspace-ID: $WORKSPACE_ID" \
  -H "Content-Type: application/json" \
  -d '{"target_status": "published", "reason": "QA approved"}'
```

### Discover agents with visibility filtering

```bash
# Query as a human user — all published agents in workspace
curl "http://localhost:8000/api/v1/agents?status=published&limit=20" \
  -H "Authorization: Bearer $JWT" \
  -H "X-Workspace-ID: $WORKSPACE_ID"

# Query with FQN pattern
curl "http://localhost:8000/api/v1/agents?fqn_pattern=finance-ops:*&status=published" \
  -H "Authorization: Bearer $JWT" \
  -H "X-Workspace-ID: $WORKSPACE_ID"

# Keyword search
curl "http://localhost:8000/api/v1/agents?keyword=compliance+verification" \
  -H "Authorization: Bearer $JWT" \
  -H "X-Workspace-ID: $WORKSPACE_ID"
```

### Attempt security-violating upload

```bash
# Create a package with path traversal attempt
mkdir -p /tmp/bad-agent
mkdir -p /tmp/bad-agent/evil
echo "evil" > /tmp/bad-agent/evil/../../../../etc/passwd 2>/dev/null || true
cat > /tmp/bad-agent/manifest.yaml << 'EOF'
local_name: evil-agent
version: 1.0.0
purpose: Testing security validation
role_types: [executor]
EOF
# Create tarball with malicious path
cd /tmp && tar -czf evil-agent.tar.gz \
  --transform 's,bad-agent/evil/../../../../etc/passwd,../../etc/passwd,' \
  bad-agent/evil 2>/dev/null || true

curl -X POST http://localhost:8000/api/v1/agents/upload \
  -H "Authorization: Bearer $JWT" \
  -H "X-Workspace-ID: $WORKSPACE_ID" \
  -F "namespace_name=finance-ops" \
  -F "package=@/tmp/evil-agent.tar.gz"

# Expect 422: {"error_type": "path_traversal", "detail": "..."}
```

---

## Integration Test Scenarios

### Scenario 1: Full registration flow
1. Create namespace `test-ns`
2. Upload valid package → verify 201, FQN = `test-ns:my-agent`, status = `draft`, revision created with digest
3. Upload same agent different version → verify 200, `created: false`, second revision created
4. GET `/api/v1/agents/{id}/revisions` → verify 2 revisions in chronological order
5. Resolve FQN `test-ns:my-agent` → verify returns profile within 200ms

### Scenario 2: Package security validation
1. Upload package with `../../etc/passwd` in tar entry → verify 422 `path_traversal`
2. Upload package with symlink entry → verify 422 `symlink_rejected`
3. Upload package >50MB → verify 422 `size_limit`
4. Upload package missing `purpose` in manifest → verify 422 `manifest_invalid`, field=`purpose`
5. Upload package with no `role_types` in manifest → verify 422 `manifest_invalid`
6. All above: verify no data in PostgreSQL, MinIO, OpenSearch

### Scenario 3: Lifecycle state machine
1. Register agent (status: draft)
2. Attempt `draft → deprecated` → verify 409 with valid transitions listed
3. Transition `draft → validated` → verify success + audit record
4. Transition `validated → published` → verify Kafka event on `registry.events`
5. Transition `published → deprecated` → verify Kafka event emitted
6. Query agent in discovery → verify deprecated agent shows deprecation notice
7. Transition `deprecated → archived` → verify agent not in discovery results but accessible by ID

### Scenario 4: Visibility filtering
1. Register 3 agents: `ns-a:agent-1`, `ns-a:agent-2`, `ns-b:agent-3` (all published)
2. Create agent-requester with `visibility_agents: []` → query discovery → verify 0 results
3. Update visibility to `["ns-a:*"]` → query discovery → verify 2 results (ns-a agents only)
4. Add workspace-level grant `["ns-b:agent-3"]` → query → verify 3 results (union)
5. Update visibility to `["*"]` → query → verify all 3 results

---

## Kafka Verification

```bash
# Listen for registry events
kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic registry.events --from-beginning

# After publishing an agent, should see:
# {
#   "event_type": "registry.agent.published",
#   "correlation": {"workspace_id": "...", ...},
#   "payload": {"fqn": "finance-ops:kyc-verifier", ...}
# }
```

---

## Database Verification

```sql
-- Check all registry tables
SELECT COUNT(*) FROM registry_namespaces;
SELECT COUNT(*) FROM registry_agent_profiles;
SELECT COUNT(*) FROM registry_agent_revisions;
SELECT COUNT(*) FROM registry_lifecycle_audit;
SELECT COUNT(*) FROM registry_maturity_records;

-- Check FQN uniqueness index
SELECT fqn, status, maturity_level FROM registry_agent_profiles ORDER BY created_at;

-- Check audit trail for an agent
SELECT previous_status, new_status, actor_id, reason, created_at
FROM registry_lifecycle_audit
WHERE agent_profile_id = '<agent_id>'
ORDER BY created_at;
```
