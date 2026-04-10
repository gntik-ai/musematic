# Research: Neo4j Knowledge Graph Deployment

**Feature**: 006-neo4j-knowledge-graph  
**Date**: 2026-04-09  
**Phase**: 0 — Pre-design research

---

## Decision 1: Neo4j Deployment Model (StatefulSet, No Operator)

**Decision**: Deploy Neo4j as a Kubernetes `StatefulSet` directly — no Kubernetes operator is used. The spec explicitly documents this: "deployed as a standard Kubernetes StatefulSet with a Helm chart, similar to the Qdrant deployment pattern (feature 005)." Production: 3-pod causal cluster (1 leader + 2 followers). Development: 1-pod standalone Community Edition. The official `neo4j/neo4j` Helm chart is the basis; a wrapper chart at `deploy/helm/neo4j/` adds the schema init Job, backup CronJob, NetworkPolicy, and Secret.

**Rationale**: The official Neo4j Helm chart (`neo4j/neo4j`) is the recommended Kubernetes deployment path. Unlike PostgreSQL (CloudNativePG) and Kafka (Strimzi), no stable, widely-adopted Neo4j operator exists for the required version (5.x). Using StatefulSet directly (via the official chart) is both the official Neo4j recommendation and consistent with Qdrant (feature 005) deployment conventions in this project.

**Alternatives considered**:
- Neo4j Kubernetes Operator (community): immature, limited Enterprise features, not pinned in constitution. Rejected.
- Bare StatefulSet without Neo4j chart: higher maintenance burden. Rejected — official chart covers pod config, clustering, and health probes.

---

## Decision 2: Neo4j Edition Selection

**Decision**: Development uses Neo4j Community Edition (single node, no clustering). Production uses Neo4j Enterprise Edition (required for causal clustering with `neo4j.causalClustering.enabled=true`). The Helm chart `values-dev.yaml` sets `edition: community` and `neo4j.minimumClusterSize: 1`. The `values-prod.yaml` sets `edition: enterprise` and `neo4j.minimumClusterSize: 3`.

**Rationale**: Causal clustering (3 nodes with leader/follower roles) is an Enterprise Edition feature. Community Edition supports only a single standalone node. The spec assumption documents this: "Development mode uses the Community Edition (single node, no clustering). Production uses the Enterprise Edition."

**Alternatives considered**:
- Single-node Enterprise for both dev and prod: Enterprise license required for dev environments is wasteful and adds cost. Rejected.
- Neo4j AuraDB (managed cloud): not a self-hosted Kubernetes solution; breaks deployment model. Rejected.

---

## Decision 3: APOC Plugin Installation

**Decision**: APOC (Awesome Procedures on Cypher) is pre-installed in the Neo4j Docker image via the `NEO4J_PLUGINS` environment variable, which the official chart supports natively: `NEO4J_PLUGINS=["apoc"]`. The APOC plugin JAR is downloaded at container startup if not cached, or the image can be pre-built with it included. No separate operator or init container is needed.

**Rationale**: The spec assumption states "The APOC plugin is pre-installed in the container image or installed via plugin configuration in the StatefulSet; it provides advanced graph algorithms." The Neo4j official Docker image supports the `NEO4J_PLUGINS` environment variable to auto-download and install plugins at startup. This is the official Neo4j-recommended approach and requires no custom image build.

**Alternatives considered**:
- Custom Docker image with APOC JAR baked in: eliminates startup download but requires maintaining a custom image. Rejected — `NEO4J_PLUGINS` env var is simpler.
- Init container to download APOC JAR: adds complexity; official `NEO4J_PLUGINS` mechanism is cleaner. Rejected.

---

## Decision 4: Schema Initialization Pattern

**Decision**: An idempotent Cypher script (`deploy/neo4j/init.cypher`) is executed by a Kubernetes `Job` (`deploy/helm/neo4j/templates/schema-init-job.yaml`) using `cypher-shell`. The Job runs post-install as a Helm hook (`helm.sh/hook: post-install,post-upgrade`). All `CREATE CONSTRAINT` and `CREATE INDEX` statements use `IF NOT EXISTS` (supported in Neo4j 5.x), making the operation idempotent. The Job retries until Neo4j is ready using an init container that polls the Bolt port.

**Rationale**: `cypher-shell` is included in the official Neo4j container image, avoiding a separate image requirement. `IF NOT EXISTS` syntax (Neo4j 5.x+) ensures the schema init Job can run on upgrade without errors. A Helm post-install/post-upgrade hook is the standard pattern for Kubernetes-native schema initialization (consistent with the Qdrant init approach in feature 005).

**Alternatives considered**:
- Python script using `neo4j-python-driver`: requires a Python container for the Job; `cypher-shell` is already in the Neo4j image. Rejected.
- Helm init container running cypher-shell: init containers block pod start, not suitable for a post-install schema operation. Rejected.
- Manual schema creation: not idempotent, not reproducible. Rejected.

---

## Decision 5: Backup via `neo4j-admin database dump`

**Decision**: A Kubernetes `CronJob` runs on schedule (default: `0 3 * * *` — daily at 03:00 UTC) and executes `neo4j-admin database dump --database=neo4j --to-path=/dumps/` inside a pod with access to the Neo4j data volume, then uploads the dump file to `s3://backups/neo4j/{timestamp}/` via a Python script using `aioboto3`. The dump runs against the primary (leader) node. Restore is documented in the quickstart as a manual operation.

**Rationale**: `neo4j-admin database dump` is the official Neo4j backup mechanism for Community and Enterprise. It produces a self-contained dump file suitable for archival. The spec requires upload to the platform's object storage at `backups/neo4j/` prefix (feature 004 dependency). Using `neo4j-admin` (included in the Neo4j image) avoids an additional backup tool.

**Alternatives considered**:
- Online backup via Neo4j Enterprise Backup Agent: Enterprise-only, requires additional configuration. Rejected in favor of offline dump approach (simpler, edition-agnostic).
- PVC snapshot: infrastructure-specific; dump is portable. Rejected.
- Qdrant snapshot API approach: Neo4j doesn't have an equivalent REST snapshot API. Not applicable.

---

## Decision 6: Python Async Client Wrapper

**Decision**: The `apps/control-plane/src/platform/common/clients/neo4j.py` file implements `AsyncNeo4jClient` using `neo4j-python-driver 5.x` with `AsyncGraphDatabase.driver()`. All Cypher queries execute via `async with driver.session() as session: await session.run(...)`. Workspace-scoped queries are enforced by a `workspace_filter` helper that prepends `WHERE n.workspace_id = $workspace_id` to all node lookups. The local mode fallback (SQLAlchemy recursive CTEs) is encapsulated behind the same interface.

**Rationale**: Constitution §2.1 mandates `neo4j-python-driver 5.x` with `AsyncGraphDatabase`. The spec architecture assumption states "the full client wrapper is not part of this feature's scope — this feature covers cluster and schema infrastructure plus a basic Python client wrapper." The basic wrapper covers: run query, create node, create relationship, traverse path, health check, and local mode fallback detection.

**Alternatives considered**:
- Sync driver: constitution mandates async everywhere. Rejected.
- `neomodel` (ORM): adds abstraction layer that conflicts with the Cypher-centric spec design. Rejected.
- Raw driver without wrapper: violates workspace isolation convention (no `workspace_filter` enforcement). Rejected.

---

## Decision 7: Network Policy

**Decision**: One `NetworkPolicy` in `platform-data` namespace:
- Bolt (7687) ingress from `platform-control` and `platform-execution` namespaces.
- HTTP admin (7474) ingress from `platform-observability` (Prometheus metrics) and `platform-control` (admin browser).
- Inter-pod (7687, 5000, 7000) within `platform-data` for causal cluster communication.

**Rationale**: Neo4j causal clustering uses port 5000 (cluster communication) and port 7000 (cluster backup). The main application port is Bolt (7687). HTTP (7474) serves the admin browser and Prometheus `/metrics` endpoint. Network policy mirrors the Qdrant pattern from feature 005.

**Alternatives considered**:
- Separate policies per namespace: more verbose, same security outcome. Rejected in favor of one policy with multiple `from` entries.

---

## Decision 8: Local Mode Fallback

**Decision**: When `NEO4J_URL` is not set (or `GRAPH_MODE=local`), `AsyncNeo4jClient` routes queries to `AsyncLocalGraphClient` which executes SQLAlchemy recursive CTEs against PostgreSQL. The CTE fallback supports a maximum of 3 hops and returns data in the same structure as Neo4j responses. Queries exceeding 3 hops raise `HopLimitExceededError`.

**Rationale**: Per spec assumption §US7 and spec FR-016. The constitution AD-3.3 explicitly allows: "except in local mode fallback" for recursive CTEs. PostgreSQL (feature 001) is always available in all deployment modes. The 3-hop limit matches the spec maximum for local mode.

**Alternatives considered**:
- SQLite: not available in the platform (PostgreSQL is the relational store). Rejected.
- Networkx in-memory graph: requires loading full graph into memory; impractical for production-scale data. Rejected.
- No fallback: breaks developer workflows. Rejected.

---

## Resolution Summary

All technical unknowns resolved. No NEEDS CLARIFICATION markers remain. Plan can proceed to Phase 1.
