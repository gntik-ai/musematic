# Research: OpenSearch Full-Text Search Deployment

**Feature**: 008-opensearch-full-text-search  
**Date**: 2026-04-10  
**Phase**: 0 — Pre-design research

---

## Decision 1: Deployment Model — Official Helm Chart (Wrapper)

**Decision**: Deploy OpenSearch using a wrapper Helm chart at `deploy/helm/opensearch/` that declares the official `opensearch-project/opensearch` chart as a dependency. The spec assumption states: "deployed as a standard Kubernetes StatefulSet with a Helm chart, similar to the Qdrant (feature 005), Neo4j (feature 006), and ClickHouse (feature 007) deployment patterns." The official OpenSearch Helm chart deploys as a StatefulSet with no operator — it is compatible with the project's established pattern.

A second chart dependency, `opensearch-project/opensearch-dashboards`, is included in the same wrapper chart to deploy the operator dashboard as a separate Deployment. This mirrors the spec assumption: "the operator dashboard is deployed as a separate lightweight deployment."

**Rationale**: The official OpenSearch Helm chart (`opensearch-project/opensearch`) is a pure StatefulSet-based chart — no operator, no CRD dependencies. Using it as a dependency (rather than a custom StatefulSet) reduces maintenance and leverages official release tracking. The wrapper chart adds project-specific resources: NetworkPolicy, ConfigMap for synonyms, Secret for credentials, init Job, and Helm values for production/development overrides.

**Alternatives considered**:
- Custom StatefulSet (no upstream chart): maximum control but duplicates all StatefulSet configuration (JVM options, discovery settings, security config). Rejected — the official chart is not operator-coupled and is well-maintained.
- Bitnami OpenSearch chart: exists but lags on version updates and uses different configuration conventions. Rejected — official chart preferred.
- OpenSearch Operator (opensearch-project/opensearch-k8s-operator): adds CRDs and controller. Constitution does not mandate it. Rejected — StatefulSet pattern is sufficient.

---

## Decision 2: Security Plugin Configuration (Dev Off, Prod On)

**Decision**: The OpenSearch security plugin is **disabled in development** (single-node, local testing) via environment variable `DISABLE_SECURITY_PLUGIN=true` in the StatefulSet. In **production**, the security plugin is enabled with an internal user database (`internal_users.yml`). A single admin user is provisioned via a Kubernetes Secret (`opensearch-credentials`) containing the admin username and bcrypt-hashed password. Platform services authenticate with HTTP Basic Auth.

**Rationale**: The spec assumption confirms this pattern: "Development mode runs a single node with security plugin disabled for ease of local testing. Production mode enables the security plugin." Disabling security in dev eliminates TLS setup complexity for local testing. An internal user database (not LDAP/SAML) is the simplest production auth that satisfies FR-009 without external dependencies.

**Alternatives considered**:
- TLS + security in dev: possible but requires certificate generation and complicates testcontainers integration. Rejected for dev.
- External LDAP/SAML: requires an external auth provider. Rejected — spec assumption specifies internal user database.
- Anonymous access in prod: security violation. Rejected.

---

## Decision 3: OpenSearch Plugins — Official Chart Installation

**Decision**: The ICU analysis plugin (`analysis-icu`) is installed at pod startup via the official chart's plugin installation mechanism before the main OpenSearch process starts. The plugin is not pre-baked into a custom Docker image, which keeps upgrades aligned with the upstream chart and OpenSearch image.

**Rationale**: Baking a custom image requires a CI pipeline and registry management for each OpenSearch version upgrade. The chart plugin installer keeps the Docker image configuration declarative in Helm values and automatically picks up the correct plugin version for each OpenSearch release. The plugins are small and install in seconds. This pattern aligns with the official OpenSearch Helm chart documentation.

**Alternatives considered**:
- Custom Docker image with plugins pre-installed: clean but adds image build/publish pipeline. Rejected — chart-managed plugin installation is simpler and self-updating.
- `OPENSEARCH_PLUGINS` env var: not a standard OpenSearch mechanism (contrast with Elasticsearch). Rejected — init container is the correct approach.
- Skip ICU plugin: would drop multilingual text analysis support (FR-016). Rejected.

---

## Decision 4: Index Lifecycle Management — OpenSearch ISM (Not Elasticsearch ILM)

**Decision**: Use OpenSearch **Index State Management (ISM)** via the `_plugins/_ism/policies` API for data retention. ISM is the OpenSearch equivalent of Elasticsearch ILM. ISM policies are created by the init Job using the `opensearch-py` client. Two policies are configured: `audit-events-policy` (retention configurable, default 90 days with rollover at 50GB or 30 days) and `connector-payloads-policy` (30-day hard delete). Marketplace agent indexes have no ISM policy (retained indefinitely).

**Rationale**: The spec references "ILM" in several places, but OpenSearch uses ISM — the feature-equivalent system. ISM supports the same operations (rollover, transition, delete) via a plugin-based API. Using ISM keeps the implementation OpenSearch-native rather than relying on Elasticsearch-compatible APIs that may not be fully supported.

**Alternatives considered**:
- Elasticsearch-compatible `_ilm/policy` API: OpenSearch supports this endpoint in compatibility mode but ISM is the native and recommended approach. Rejected — ISM is the correct OpenSearch primitive.
- CronJob deleting old indexes: manual deletion via a cron job. Rejected — ISM is declarative and integrated.
- TTL-based document expiry: not supported by OpenSearch at the document level. Rejected.

---

## Decision 5: Index Template Init — Python Script Job (Idempotent PUT)

**Decision**: A Kubernetes Job (Helm post-install/post-upgrade hook) runs a Python script using `opensearch-py 2.x` async client to:
1. Create ISM policies via `PUT _plugins/_ism/policies/{policy}` (idempotent)
2. Create index templates via `PUT _index_template/{template}` (composable templates, idempotent — overwrites existing)
3. Register snapshot repository via `PUT _snapshot/{repository}` (idempotent)

The init script lives at `deploy/opensearch/init/init_opensearch.py`. A dedicated container image (Python slim + opensearch-py) runs the Job.

**Rationale**: Python scripting is the natural choice for the init Job given the project's Python control plane. The composable template API (`_index_template`, not the legacy `_template`) is the current OpenSearch standard and supports component templates for reuse. Using PUT (not POST) for all resources makes the init idempotent — running it again on upgrade applies any changes without errors.

**Alternatives considered**:
- JSON files + curl: simpler but requires a curl-capable init container and loses error handling and retry logic. Rejected.
- `opensearch-cli` tool: OpenSearch's official CLI. Not as scriptable as Python; error handling is limited. Rejected.
- Helm hooks with raw API calls: complex templating required. Rejected.

---

## Decision 6: Synonym Dictionary — ConfigMap-Mounted File

**Decision**: The synonym dictionary is stored as a file in a Kubernetes ConfigMap (`opensearch-synonyms`) mounted into each OpenSearch pod at `/usr/share/opensearch/config/synonyms/agent-synonyms.txt`. The `marketplace-agents` template uses an index-time analyzer without synonyms and a search-time analyzer (`agent_analyzer`) that references this file path. The initial dictionary contains the three synonym groups specified in the spec. Administrators update synonyms by editing the ConfigMap; an index close/open or analyzer reload is required for changes to take effect.

**Rationale**: The spec assumption confirms: "Synonym dictionaries are stored as files in the container image or mounted via ConfigMap." The ConfigMap approach avoids rebuilding the container image for synonym updates. The file path is fixed so the index template can reference it statically. The requirement to close/open or reindex after synonym updates is documented in the spec assumptions and reflected in the quickstart.

**Alternatives considered**:
- Inline synonyms in the index template (`synonyms` array in the filter config): simpler but requires reindex for every update and is stored in the template (not separately manageable). Rejected — ConfigMap is more operationally flexible.
- External synonym service: overkill. Rejected.
- Custom container image with synonyms baked in: requires image rebuild for updates. Rejected.

---

## Decision 7: Snapshot Backup — S3 Plugin + Snapshot Management (SM)

**Decision**: OpenSearch snapshots are stored in MinIO (feature 004) at the `backups/opensearch/` prefix using the **S3 repository plugin** (`repository-s3`) installed by the wrapper chart alongside `analysis-icu`. The snapshot repository is registered at init time. Automated daily snapshots are scheduled using **OpenSearch Snapshot Management (SM)** via the `_plugins/_sm/policies` API — this is OpenSearch's native snapshot scheduler. Manual snapshots can be triggered via the OpenSearch REST API or Dashboards UI.

**Rationale**: The wrapper chart installs `repository-s3` alongside `analysis-icu` so the cluster can register a MinIO-backed snapshot repository without a custom image. OpenSearch SM (Snapshot Management) provides native cron-scheduled snapshots without requiring an external CronJob. SM policies are created by the init Job. Using SM over a Kubernetes CronJob keeps snapshot management inside OpenSearch where failures are observable via the Dashboards UI.

**Alternatives considered**:
- Kubernetes CronJob calling `PUT _snapshot/{repo}/{snapshot}`: external scheduler, harder to observe. Rejected — SM is the native approach.
- Elasticsearch-compatible snapshot API: OpenSearch supports it natively via the S3 plugin. This is the approach used.
- Velero for cluster-level backup: backs up Kubernetes resources, not OpenSearch index data. Rejected.

---

## Decision 8: Python Async Client — AsyncOpenSearch

**Decision**: The Python client wrapper uses `AsyncOpenSearch` from `opensearch-py 2.x`, configured with `http_auth=(user, password)` and `use_ssl=False` in dev / `use_ssl=True` in prod. The wrapper class `AsyncOpenSearchClient` at `apps/control-plane/src/platform/common/clients/opensearch.py` exposes typed methods: `index_document`, `bulk_index`, `search`, `delete_document`, `health_check`, `close`. All methods are `async`. Connection pooling is handled by the underlying `AsyncHttpConnection` transport.

**Rationale**: Constitution §2.1 mandates `opensearch-py 2.x` async client. `AsyncOpenSearch` is the async variant provided by the same package. Using the async client is consistent with the project's "async everywhere" principle. The wrapper class follows the same pattern as `AsyncNeo4jClient`, `AsyncQdrantClient`, and `AsyncClickHouseClient` in the project.

**Alternatives considered**:
- Synchronous `OpenSearch` client wrapped in `asyncio.run_in_executor`: works but not truly async. Rejected — `AsyncOpenSearch` is available.
- elasticsearch-py: compatible with OpenSearch via compatibility mode but misleading naming; opensearch-py is the correct client. Rejected.
- httpx directly against the REST API: bypasses the client abstraction layer. Rejected.

---

## Decision 9: Network Policy — Authorized Namespace Allowlist

**Decision**: A Kubernetes `NetworkPolicy` restricts ingress to the OpenSearch pods on port `9200` (REST) from two namespaces: `platform-control` and `platform-execution`. Ingress on port `9600` (Performance Analyzer metrics) is allowed from `platform-observability`. The OpenSearch Dashboards Deployment (in `platform-data`) connects to OpenSearch on port `9200` via a network policy exception for same-namespace traffic. All other ingress is denied by default.

**Rationale**: FR-011 and US7 require namespace-based access control. The NetworkPolicy follows the same pattern as other data stores in the project. Separating ports for REST (9200) and metrics (9600) allows the observability stack to scrape metrics without full API access.

**Alternatives considered**:
- IP-based firewall rules: harder to manage in dynamic pod environments. Rejected.
- Service mesh mTLS (Istio/Linkerd): adds infrastructure complexity. Constitution does not mandate a service mesh. Rejected.
- No network policy (rely on security plugin auth): defense-in-depth requires network isolation. Rejected.
