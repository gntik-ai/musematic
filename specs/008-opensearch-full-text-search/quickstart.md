# Quickstart: OpenSearch Full-Text Search Deployment

**Feature**: 008-opensearch-full-text-search  
**Date**: 2026-04-10

---

## Prerequisites

- Kubernetes cluster (1.28+) with `platform-data` namespace
- Helm 3.x installed and configured
- MinIO (feature 004) deployed — provides `musematic-backups` bucket for snapshots
- `kubectl` context pointing to the target cluster

---

## 1. Add the OpenSearch Helm Repository

```bash
helm repo add opensearch https://opensearch-project.github.io/helm-charts
helm repo update
```

---

## 2. Deploy (Development — Single Node, Security Disabled)

```bash
helm install musematic-opensearch deploy/helm/opensearch \
  -n platform-data \
  -f deploy/helm/opensearch/values-dev.yaml \
  --wait --timeout 5m
```

Expected output:
- `musematic-opensearch-0` pod Running
- `musematic-opensearch-dashboards-*` pod Running
- `opensearch-init` Job Completed

---

## 3. Deploy (Production — 3 Nodes, Security Enabled)

```bash
# Create credentials secret before deploying
kubectl create secret generic opensearch-credentials \
  -n platform-data \
  --from-literal=OPENSEARCH_USERNAME=admin \
  --from-literal=OPENSEARCH_PASSWORD='<strong-password>'

helm install musematic-opensearch deploy/helm/opensearch \
  -n platform-data \
  -f deploy/helm/opensearch/values-prod.yaml \
  --wait --timeout 10m
```

Expected output:
- `musematic-opensearch-0`, `-1`, `-2` pods Running
- Cluster health: green

---

## 4. Verify Cluster Health

```bash
# Port-forward for local access
kubectl port-forward svc/musematic-opensearch 9200:9200 -n platform-data &

# Check cluster health (green = all replicas assigned; yellow = single-node OK)
curl -s http://localhost:9200/_cluster/health | python3 -m json.tool

# Expected in dev:
# {
#   "status": "yellow",  <-- expected: 1 node can't assign replicas
#   "number_of_nodes": 1,
#   "number_of_data_nodes": 1
# }

# Expected in prod:
# {
#   "status": "green",
#   "number_of_nodes": 3,
#   "number_of_data_nodes": 3
# }
```

---

## 5. Verify Index Templates

```bash
# List all index templates (expect: marketplace-agents, audit-events, connector-payloads)
curl -s http://localhost:9200/_index_template | python3 -m json.tool | grep '"name"'

# Inspect marketplace-agents template
curl -s http://localhost:9200/_index_template/marketplace-agents | python3 -m json.tool
```

---

## 6. Verify ISM Policies

```bash
# List ISM policies (expect: audit-events-policy, connector-payloads-policy)
curl -s http://localhost:9200/_plugins/_ism/policies | python3 -m json.tool
```

---

## 7. Test ICU Analyzer (Synonym Expansion)

```bash
# Test the agent_analyzer — verify synonym expansion
curl -s -X POST http://localhost:9200/marketplace-agents-000001/_analyze \
  -H 'Content-Type: application/json' \
  -d '{
    "analyzer": "agent_analyzer",
    "text": "summarizer"
  }' | python3 -m json.tool

# Expected tokens should include: "summarizer", "text", "summary", "agent", "summarization"
```

---

## 8. Test Index and Search

```bash
# Index a test agent document
curl -s -X PUT http://localhost:9200/marketplace-agents-000001/_doc/test-agent-1 \
  -H 'Content-Type: application/json' \
  -d '{
    "agent_id": "test-agent-1",
    "name": "Text Summary Agent",
    "purpose": "Summarizes long documents into key points",
    "description": "A summarization agent that condenses input text",
    "tags": ["nlp", "text-processing"],
    "capabilities": ["summarization", "nlp"],
    "maturity_level": 3,
    "trust_score": 0.85,
    "workspace_id": "ws-test",
    "lifecycle_state": "active",
    "certification_status": "certified",
    "publisher_id": "pub-1",
    "fqn": "test:text-summary-agent",
    "indexed_at": "2026-04-10T00:00:00Z",
    "updated_at": "2026-04-10T00:00:00Z"
  }' | python3 -m json.tool

# Refresh the index so the document is searchable immediately
curl -s -X POST http://localhost:9200/marketplace-agents-000001/_refresh

# Search for "summarizer" — should match "Text Summary Agent" via synonyms
curl -s -X POST http://localhost:9200/marketplace-agents-000001/_search \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "bool": {
        "must": [{
          "multi_match": {
            "query": "summarizer",
            "fields": ["name^3", "purpose^2", "description", "tags"],
            "analyzer": "agent_analyzer"
          }
        }],
        "filter": [{ "term": { "workspace_id": "ws-test" } }]
      }
    }
  }' | python3 -m json.tool

# Expected: hits.total.value = 1, _source.name = "Text Summary Agent"
```

---

## 9. Test Faceted Aggregation

```bash
curl -s -X POST http://localhost:9200/marketplace-agents-000001/_search \
  -H 'Content-Type: application/json' \
  -d '{
    "query": { "bool": { "filter": [{ "term": { "workspace_id": "ws-test" } }] } },
    "aggs": {
      "by_capability": { "terms": { "field": "capabilities", "size": 10 } },
      "by_maturity":   { "terms": { "field": "maturity_level", "size": 5 } }
    },
    "size": 0
  }' | python3 -m json.tool

# Expected: aggregations.by_capability.buckets includes "summarization" with doc_count=1
```

---

## 10. Test Workspace Isolation

```bash
# Index agent in workspace ws-other
curl -s -X PUT http://localhost:9200/marketplace-agents-000001/_doc/other-agent \
  -H 'Content-Type: application/json' \
  -d '{ "agent_id": "other-agent", "workspace_id": "ws-other", "name": "Other Agent", ... }'
curl -s -X POST http://localhost:9200/marketplace-agents-000001/_refresh

# Search with ws-test filter — must NOT return ws-other documents
curl -s -X POST http://localhost:9200/marketplace-agents-000001/_search \
  -H 'Content-Type: application/json' \
  -d '{ "query": { "bool": { "filter": [{ "term": { "workspace_id": "ws-test" } }] } } }' \
  | python3 -c "import sys,json; r=json.load(sys.stdin); assert r['hits']['total']['value'] == 1; print('Workspace isolation: PASS')"
```

---

## 11. Verify Snapshot Repository

```bash
# Check snapshot repository is registered
curl -s http://localhost:9200/_snapshot/opensearch-backups | python3 -m json.tool

# Trigger a manual snapshot
curl -s -X PUT http://localhost:9200/_snapshot/opensearch-backups/manual-test-1 \
  -H 'Content-Type: application/json' \
  -d '{ "indices": "*", "ignore_unavailable": true, "include_global_state": false }'

# Check snapshot status (wait ~30s then verify)
sleep 30
curl -s http://localhost:9200/_snapshot/opensearch-backups/manual-test-1 | python3 -m json.tool
# Expected: "state": "SUCCESS"
```

---

## 12. Access OpenSearch Dashboards

```bash
kubectl port-forward svc/musematic-opensearch-dashboards 5601:5601 -n platform-data &
open http://localhost:5601
```

Login credentials (prod): admin / `<password from secret>`  
Dev: no authentication required.

Navigate to **Index Management** → **Indices** to verify all three initial indexes exist.  
Navigate to **Dev Tools** to run ad-hoc queries.

---

## 13. Run Integration Tests

```bash
cd apps/control-plane

# Start test container (testcontainers spins up OpenSearch automatically)
pytest tests/integration/test_opensearch_basic.py -v
pytest tests/integration/test_opensearch_search.py -v
pytest tests/integration/test_opensearch_facets.py -v
pytest tests/integration/test_opensearch_synonyms.py -v
```

---

## 14. Updating Synonyms

To add new synonyms:

1. Edit the ConfigMap:
   ```bash
   kubectl edit configmap opensearch-synonyms -n platform-data
   ```
   Add new lines to `agent-synonyms.txt` in `synonyms: key key key` format.

2. Reload synonyms by closing and reopening the index (no data loss):
   ```bash
   curl -X POST http://localhost:9200/marketplace-agents-000001/_close
   curl -X POST http://localhost:9200/marketplace-agents-000001/_open
   ```

3. Verify the new synonyms are active with the analyzer test in section 7.

> **Note**: The `updateable: true` setting in the synonym filter allows synonym reload via `_reload_search_analyzers` API without closing the index, but only when using a file-based synonym source.

---

## 15. Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Init Job fails with connection refused | OpenSearch not yet ready | Check pod readiness; increase `initJob.backoff` |
| Analyzer test returns no synonym tokens | ICU plugin not installed | Check init container logs for plugin install errors |
| Cluster health: red | Shard allocation failure | Check `GET /_cluster/allocation/explain` |
| Dashboards shows "Unable to connect" | Security config mismatch | Ensure `DISABLE_SECURITY_DASHBOARDS_PLUGIN` matches `DISABLE_SECURITY_PLUGIN` |
| Snapshot fails with S3 error | MinIO unreachable or bucket missing | Verify feature 004 (minio-object-storage) is deployed |
