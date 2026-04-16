# Contract: OpenSearch Cluster Infrastructure

**Feature**: 008-opensearch-full-text-search  
**Date**: 2026-04-10  
**Type**: Infrastructure Contract

---

## 1. Cluster Identity

| Property | Value |
|----------|-------|
| Service name | `musematic-opensearch` |
| Namespace | `platform-data` |
| REST endpoint | `http://musematic-opensearch.platform-data:9200` |
| Dashboards endpoint | `http://musematic-opensearch-dashboards.platform-data:5601` |
| OpenSearch version | `2.18.x` |
| Production topology | 3 nodes (all master-eligible + data roles) |
| Development topology | 1 standalone node (`discovery.type=single-node`) |

---

## 2. Authentication

| Environment | Method | Credential Source |
|-------------|--------|-------------------|
| Production | HTTP Basic Auth (admin user) | Kubernetes Secret `opensearch-credentials` |
| Development | None (security plugin disabled) | N/A |

**Secret schema**:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: opensearch-credentials
  namespace: platform-data
type: Opaque
stringData:
  OPENSEARCH_USERNAME: admin
  OPENSEARCH_PASSWORD: <bcrypt-hashed, ≥16 chars>
```

---

## 3. Provisioned Index Templates

| Template Name | Pattern | ISM Policy | Analyzer |
|---------------|---------|------------|----------|
| `marketplace-agents` | `marketplace-agents-*` | None (indefinite) | `agent_index_analyzer` for indexing, `agent_analyzer` for search |
| `audit-events` | `audit-events-*` | `audit-events-policy` | `standard` |
| `connector-payloads` | `connector-payloads-*` | `connector-payloads-policy` | `standard` |

**Initial default indexes** created by the init Job:
- `marketplace-agents-000001` (aliased from `marketplace-agents`)
- `audit-events-000001` (aliased from `audit-events`, ISM rollover starts here)
- `connector-payloads-000001` (aliased from `connector-payloads`, ISM rollover starts here)

---

## 4. ISM Policies

| Policy | Trigger | Action |
|--------|---------|--------|
| `audit-events-policy` | 50GB or 30 days age → rollover; 90 days → delete | Automatic via OpenSearch ISM |
| `connector-payloads-policy` | 30 days → delete | Automatic via OpenSearch ISM |

---

## 5. Snapshot Repository

| Property | Value |
|----------|-------|
| Repository name | `opensearch-backups` |
| Type | S3-compatible (MinIO, feature 004) |
| Bucket | `backups` |
| Base path | `backups/opensearch/` |
| Endpoint | `http://musematic-minio.platform-data:9000` |
| Schedule | Daily at 05:00 UTC (OpenSearch SM policy) |
| Retention | 30 snapshots max, 30 days max age |

---

## 6. Custom Analyzers — `agent_index_analyzer` and `agent_analyzer`

Available on the `marketplace-agents-*` index pattern:

| Analyzer | Stage | Components | Effect |
|----------|-------|------------|--------|
| `agent_index_analyzer` | Index time | `standard` + `lowercase` + `icu_folding` | Normalized indexing without updateable synonyms |
| `agent_analyzer` | Search time | `standard` + `lowercase` + `icu_folding` + `synonym_filter` | Query-time synonym expansion from `synonyms/agent-synonyms.txt` |

**Synonym file**: mounted at `/usr/share/opensearch/config/synonyms/agent-synonyms.txt` via ConfigMap `opensearch-synonyms`. Updates require index close/open or reindex.

---

## 7. Network Access

| Source Namespace | Allowed Ports | Purpose |
|-----------------|---------------|---------|
| `platform-control` | 9200 | Control plane API queries |
| `platform-execution` | 9200 | Execution engine queries |
| `platform-data` (same namespace) | 9200 | OpenSearch Dashboards |
| `platform-observability` | 9600 | Performance Analyzer metrics scrape |
| All others | — | Blocked by NetworkPolicy |

---

## 8. Health Verification (Post-Deploy)

After deploying with `helm install` or `helm upgrade`, the following commands verify cluster readiness:

```bash
# Cluster health (expect: green for prod, yellow for dev single-node)
curl http://musematic-opensearch.platform-data:9200/_cluster/health?pretty

# List index templates (expect: marketplace-agents, audit-events, connector-payloads)
curl http://musematic-opensearch.platform-data:9200/_index_template?pretty

# List ISM policies (expect: audit-events-policy, connector-payloads-policy)
curl http://musematic-opensearch.platform-data:9200/_plugins/_ism/policies?pretty

# Snapshot repository (expect: opensearch-backups, type: s3)
curl http://musematic-opensearch.platform-data:9200/_snapshot/opensearch-backups?pretty
```

---

## 9. Constraints

- JVM heap is always 50% of pod memory limit (max 32GB per node per spec FR-001).
- Security plugin state (`DISABLE_SECURITY_PLUGIN`) must match Dashboards security state (`DISABLE_SECURITY_DASHBOARDS_PLUGIN`).
- The `analysis-icu` plugin must be installed before index templates are applied (wrapper chart plugin installation runs before OpenSearch starts).
- Synonym dictionary updates (ConfigMap change) require manual index close/open or reindex — they do not apply automatically.
- The `repository-s3` plugin must be installed before registering the MinIO-backed snapshot repository.
