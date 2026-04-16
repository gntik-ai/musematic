# Data Model: OpenSearch Full-Text Search Deployment

**Feature**: 008-opensearch-full-text-search  
**Date**: 2026-04-10  
**Phase**: 1 — Design & Contracts

---

## 1. Index Templates and Mappings

### 1.1 `marketplace-agents` Index Template

**Pattern**: `marketplace-agents-*`  
**ISM Policy**: None (retained indefinitely)  
**Analyzers**:
- `agent_index_analyzer` for index-time normalization (lowercase + ICU folding)
- `agent_analyzer` for search-time synonym expansion (lowercase + ICU folding + synonyms)

```json
{
  "index_patterns": ["marketplace-agents-*"],
  "template": {
    "settings": {
      "number_of_shards": 2,
      "number_of_replicas": 1,
      "analysis": {
        "filter": {
          "synonym_filter": {
            "type": "synonym",
            "synonyms_path": "synonyms/agent-synonyms.txt",
            "updateable": true
          },
          "icu_folding": {
            "type": "icu_folding"
          }
        },
        "analyzer": {
          "agent_index_analyzer": {
            "type": "custom",
            "tokenizer": "standard",
            "filter": ["lowercase", "icu_folding"]
          },
          "agent_analyzer": {
            "type": "custom",
            "tokenizer": "standard",
            "filter": ["lowercase", "icu_folding", "synonym_filter"]
          }
        }
      }
    },
    "mappings": {
      "properties": {
        "agent_id":            { "type": "keyword" },
        "name":                { "type": "text", "analyzer": "agent_index_analyzer", "search_analyzer": "agent_analyzer", "fields": { "keyword": { "type": "keyword" } } },
        "purpose":             { "type": "text", "analyzer": "agent_index_analyzer", "search_analyzer": "agent_analyzer" },
        "description":         { "type": "text", "analyzer": "agent_index_analyzer", "search_analyzer": "agent_analyzer" },
        "tags":                { "type": "keyword" },
        "capabilities":        { "type": "keyword" },
        "maturity_level":      { "type": "integer" },
        "trust_score":         { "type": "float" },
        "workspace_id":        { "type": "keyword" },
        "lifecycle_state":     { "type": "keyword" },
        "certification_status":{ "type": "keyword" },
        "publisher_id":        { "type": "keyword" },
        "fqn":                 { "type": "keyword" },
        "indexed_at":          { "type": "date" },
        "updated_at":          { "type": "date" }
      }
    }
  }
}
```

**Synonym file** (`synonyms/agent-synonyms.txt` — mounted via ConfigMap):

```
summarizer, text summary agent, summarization
translator, language translation, translation agent
classifier, categorizer, classification agent
```

---

### 1.2 `audit-events` Index Template

**Pattern**: `audit-events-*`  
**ISM Policy**: `audit-events-policy` (rollover at 50GB or 30 days; delete after 90 days)

```json
{
  "index_patterns": ["audit-events-*"],
  "template": {
    "settings": {
      "number_of_shards": 2,
      "number_of_replicas": 1,
      "plugins.index_state_management.policy_id": "audit-events-policy"
    },
    "mappings": {
      "properties": {
        "event_id":      { "type": "keyword" },
        "event_type":    { "type": "keyword" },
        "actor_id":      { "type": "keyword" },
        "actor_type":    { "type": "keyword" },
        "timestamp":     { "type": "date" },
        "workspace_id":  { "type": "keyword" },
        "resource_type": { "type": "keyword" },
        "action":        { "type": "keyword" },
        "details":       { "type": "text", "analyzer": "standard" },
        "indexed_at":    { "type": "date" }
      }
    }
  }
}
```

---

### 1.3 `connector-payloads` Index Template

**Pattern**: `connector-payloads-*`  
**ISM Policy**: `connector-payloads-policy` (delete after 30 days)

```json
{
  "index_patterns": ["connector-payloads-*"],
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 1,
      "plugins.index_state_management.policy_id": "connector-payloads-policy"
    },
    "mappings": {
      "properties": {
        "payload_id":       { "type": "keyword" },
        "connector_type":   { "type": "keyword" },
        "workspace_id":     { "type": "keyword" },
        "timestamp":        { "type": "date" },
        "payload_text":     { "type": "text", "analyzer": "standard" },
        "direction":        { "type": "keyword" },
        "indexed_at":       { "type": "date" }
      }
    }
  }
}
```

---

## 2. ISM Policies

### 2.1 `audit-events-policy`

```json
{
  "policy": {
    "description": "Audit events: rollover at 50GB or 30 days, delete after 90 days",
    "default_state": "hot",
    "states": [
      {
        "name": "hot",
        "actions": [{ "rollover": { "min_size": "50gb", "min_index_age": "30d" } }],
        "transitions": [{ "state_name": "delete", "conditions": { "min_index_age": "90d" } }]
      },
      {
        "name": "delete",
        "actions": [{ "delete": {} }],
        "transitions": []
      }
    ],
    "ism_template": [{ "index_patterns": ["audit-events-*"], "priority": 100 }]
  }
}
```

### 2.2 `connector-payloads-policy`

```json
{
  "policy": {
    "description": "Connector payloads: delete after 30 days",
    "default_state": "hot",
    "states": [
      {
        "name": "hot",
        "actions": [],
        "transitions": [{ "state_name": "delete", "conditions": { "min_index_age": "30d" } }]
      },
      {
        "name": "delete",
        "actions": [{ "delete": {} }],
        "transitions": []
      }
    ],
    "ism_template": [{ "index_patterns": ["connector-payloads-*"], "priority": 100 }]
  }
}
```

---

## 3. Snapshot Management (SM) Policy

```json
{
  "snapshot-management": {
    "description": "Daily snapshot at 05:00 UTC to MinIO backups/opensearch/",
    "creation": {
      "schedule": { "cron": { "expression": "0 5 * * *", "timezone": "UTC" } },
      "time_limit": "1h"
    },
    "deletion": {
      "schedule": { "cron": { "expression": "0 6 * * *", "timezone": "UTC" } },
      "time_limit": "30m",
      "condition": { "max_count": 30, "max_age": "30d" }
    },
    "snapshot_config": {
      "repository": "opensearch-backups",
      "indices": "*",
      "ignore_unavailable": true,
      "include_global_state": false
    }
  }
}
```

---

## 4. Helm Values Schema

### 4.1 `values.yaml` — Shared Defaults

```yaml
# Wrapper chart metadata
nameOverride: "musematic-opensearch"

opensearch:
  # From opensearch-project/opensearch chart
  replicas: 1
  image:
    repository: opensearchproject/opensearch
    tag: "2.18.0"
  
  # JVM heap: set via OPENSEARCH_JAVA_OPTS
  extraEnvs:
    - name: OPENSEARCH_JAVA_OPTS
      value: "-Xms1g -Xmx1g"
    - name: DISABLE_SECURITY_PLUGIN
      value: "false"
  
  # Plugins installed by the wrapper chart before OpenSearch starts
  plugins:
    enabled: true
    installList:
      - analysis-icu
      - repository-s3

  # Synonym ConfigMap mount
  extraVolumes:
    - name: synonyms
      configMap:
        name: opensearch-synonyms
  extraVolumeMounts:
    - name: synonyms
      mountPath: /usr/share/opensearch/config/synonyms

  # Persistence
  persistence:
    enabled: true
    size: 10Gi
    storageClass: ""

  # Service
  service:
    type: ClusterIP
    port: 9200

  # Resources (dev defaults)
  resources:
    requests:
      cpu: "500m"
      memory: "2Gi"
    limits:
      cpu: "1"
      memory: "2Gi"

opensearch-dashboards:
  enabled: true
  image:
    repository: opensearchproject/opensearch-dashboards
    tag: "2.18.0"
  extraEnvs:
    - name: OPENSEARCH_HOSTS
      value: '["http://musematic-opensearch:9200"]'
    - name: DISABLE_SECURITY_DASHBOARDS_PLUGIN
      value: "false"
  resources:
    requests:
      cpu: "200m"
      memory: "512Mi"
    limits:
      cpu: "500m"
      memory: "512Mi"

# Init job config
initJob:
  image: python:3.12-slim
  opensearchUrl: "http://musematic-opensearch:9200"
  snapshotRepository:
    name: "opensearch-backups"
    bucket: "backups"
    basePath: "backups/opensearch"
    minioEndpoint: "http://musematic-minio:9000"
```

### 4.2 `values-prod.yaml` — Production Overrides

```yaml
opensearch:
  replicas: 3
  
  # Role-based node configuration
  roles:
    - master
    - data
    - ingest
  
  # Master-eligible: first node only (via cluster.initial_master_nodes)
  masterService: musematic-opensearch-master
  
  extraEnvs:
    - name: OPENSEARCH_JAVA_OPTS
      value: "-Xms8g -Xmx8g"
    - name: DISABLE_SECURITY_PLUGIN
      value: "false"
  
  persistence:
    size: 100Gi
    storageClass: "fast"
  
  resources:
    requests:
      cpu: "2"
      memory: "16Gi"
    limits:
      cpu: "4"
      memory: "16Gi"

opensearch-dashboards:
  extraEnvs:
    - name: OPENSEARCH_HOSTS
      value: '["https://musematic-opensearch:9200"]'
    - name: DISABLE_SECURITY_DASHBOARDS_PLUGIN
      value: "false"
```

### 4.3 `values-dev.yaml` — Development Overrides

```yaml
opensearch:
  replicas: 1
  
  extraEnvs:
    - name: OPENSEARCH_JAVA_OPTS
      value: "-Xms512m -Xmx512m"
    - name: DISABLE_SECURITY_PLUGIN
      value: "true"
    - name: discovery.type
      value: single-node

  persistence:
    size: 5Gi

  resources:
    requests:
      cpu: "250m"
      memory: "1Gi"
    limits:
      cpu: "500m"
      memory: "1Gi"

opensearch-dashboards:
  extraEnvs:
    - name: OPENSEARCH_HOSTS
      value: '["http://musematic-opensearch:9200"]'
    - name: DISABLE_SECURITY_DASHBOARDS_PLUGIN
      value: "true"

initJob:
  opensearchUrl: "http://musearch-opensearch:9200"
```

---

## 5. Kubernetes Resources

| Resource | Type | Name | Purpose |
|----------|------|------|---------|
| StatefulSet | StatefulSet | `musematic-opensearch` | OpenSearch cluster nodes (1 dev, 3 prod) |
| Deployment | Deployment | `musematic-opensearch-dashboards` | Operator dashboard UI |
| ConfigMap | ConfigMap | `opensearch-synonyms` | `agent-synonyms.txt` synonym file |
| Secret | Secret | `opensearch-credentials` | Admin username + password |
| Job | Job | `opensearch-init` | ISM policies, index templates, snapshot repo |
| NetworkPolicy | NetworkPolicy | `opensearch-network-policy` | Ingress allowlist (platform-control, platform-execution) |
| Service | Service | `musematic-opensearch` | ClusterIP on port 9200 |
| Service | Service | `musematic-opensearch-dashboards` | ClusterIP on port 5601 |

---

## 6. Python Client Interface — `AsyncOpenSearchClient`

**Location**: `apps/control-plane/src/platform/common/clients/opensearch.py`  
**Package**: `opensearch-py 2.x` (`AsyncOpenSearch`)

```python
class AsyncOpenSearchClient:
    """Async OpenSearch client wrapper for the Agentic Mesh Platform."""

    def __init__(
        self,
        hosts: list[str],
        http_auth: tuple[str, str] | None = None,
        use_ssl: bool = False,
        verify_certs: bool = False,
    ) -> None: ...

    async def index_document(
        self,
        index: str,
        document: dict,
        document_id: str | None = None,
    ) -> str:
        """Index a single document. Returns the document ID."""

    async def bulk_index(
        self,
        index: str,
        documents: list[dict],
        id_field: str = "agent_id",
    ) -> BulkIndexResult:
        """Bulk index documents. Returns success/failure counts."""

    async def search(
        self,
        index: str,
        query: dict,
        filters: list[dict] | None = None,
        aggregations: dict | None = None,
        from_: int = 0,
        size: int = 10,
        sort: list[dict] | None = None,
    ) -> SearchResult:
        """Execute a search query with optional filters and aggregations."""

    async def search_after(
        self,
        index: str,
        query: dict,
        sort: list[dict],
        search_after: list | None = None,
        size: int = 10,
    ) -> SearchResult:
        """Deep pagination using search_after cursor."""

    async def delete_document(
        self,
        index: str,
        document_id: str,
    ) -> bool:
        """Delete a document by ID. Returns True if deleted."""

    async def delete_by_query(
        self,
        index: str,
        query: dict,
    ) -> int:
        """Delete documents matching a query. Returns deleted count."""

    async def health_check(self) -> ClusterHealth:
        """Return cluster health status (green/yellow/red)."""

    async def close(self) -> None:
        """Close the connection pool."""


# Result types
@dataclass
class SearchResult:
    hits: list[dict]
    total: int
    aggregations: dict | None
    took_ms: int
    search_after: list | None  # cursor for deep pagination

@dataclass
class BulkIndexResult:
    indexed: int
    failed: int
    errors: list[dict]

@dataclass
class ClusterHealth:
    status: str   # "green" | "yellow" | "red"
    nodes: int
    active_shards: int
    relocating_shards: int


# Exceptions
class OpenSearchClientError(Exception): ...
class OpenSearchConnectionError(OpenSearchClientError): ...
class OpenSearchIndexError(OpenSearchClientError): ...
class OpenSearchQueryError(OpenSearchClientError): ...
```

---

## 7. Search Projection Writer Interface

**Location**: `apps/control-plane/src/platform/search/projections.py`

```python
class AgentSearchProjection:
    """Event-driven index writer — projects registry events into OpenSearch."""

    async def index_agent(self, agent_profile: AgentProfile) -> None:
        """Index or update an agent profile document."""

    async def delete_agent(self, agent_id: str, workspace_id: str) -> None:
        """Remove an agent from the search index."""

    async def bulk_reindex(self, agents: list[AgentProfile]) -> BulkIndexResult:
        """Reindex a batch of agents (used for full reindex operations)."""


class AuditSearchProjection:
    """Projects audit events into the audit-events index."""

    async def index_event(self, event: AuditEvent) -> None:
        """Index a single audit event document."""


# Query builder helpers (workspace-scoped)
def build_agent_query(
    query_text: str,
    workspace_id: str,
    capabilities: list[str] | None = None,
    maturity_level: int | None = None,
    lifecycle_state: str | None = None,
    certification_status: str | None = None,
) -> dict:
    """Build a workspace-scoped BM25 search query with filters."""

def build_agent_aggregations() -> dict:
    """Build standard faceted aggregation DSL for agent search."""
```

---

## 8. Query Patterns

### 8.1 Marketplace Agent Search (BM25 + Filters + Facets)

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "agent that summarizes text",
            "fields": ["name^3", "purpose^2", "description", "tags"],
            "type": "best_fields",
            "analyzer": "agent_analyzer"
          }
        }
      ],
      "filter": [
        { "term": { "workspace_id": "ws-123" } },
        { "term": { "lifecycle_state": "active" } }
      ]
    }
  },
  "aggs": {
    "by_capability": { "terms": { "field": "capabilities", "size": 20 } },
    "by_maturity":   { "terms": { "field": "maturity_level", "size": 5 } },
    "by_lifecycle":  { "terms": { "field": "lifecycle_state", "size": 5 } },
    "by_cert":       { "terms": { "field": "certification_status", "size": 5 } },
    "trust_ranges":  {
      "range": {
        "field": "trust_score",
        "ranges": [
          { "to": 0.4, "key": "low" },
          { "from": 0.4, "to": 0.7, "key": "medium" },
          { "from": 0.7, "key": "high" }
        ]
      }
    }
  },
  "from": 0,
  "size": 10
}
```

### 8.2 Audit Event Search (Filter + Time Range)

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "workspace_id": "ws-123" } },
        { "term": { "event_type": "AGENT_REVOKED" } },
        { "range": { "timestamp": { "gte": "2026-01-01", "lte": "2026-03-31" } } }
      ]
    }
  },
  "sort": [{ "timestamp": { "order": "desc" } }]
}
```
