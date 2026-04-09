# Feature Specification: Qdrant Vector Search Deployment

**Feature Branch**: `005-qdrant-vector-search`
**Created**: 2026-04-09
**Status**: Draft
**Input**: User description: Deploy Qdrant as the dedicated vector search engine for semantic memory retrieval, agent recommendation, embedding-based similarity testing, context quality scoring, and pattern matching.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Platform Operator Deploys Vector Search Cluster (Priority: P1)

A platform operator deploys a production-ready vector search cluster with a single command. In production, the cluster runs 3 nodes with replication factor 2 for data durability and high availability. In development, a single node runs for local testing. The operator can verify cluster health through built-in metrics exposed to the monitoring stack and a REST health endpoint.

**Why this priority**: Without the running cluster, no service can store or retrieve vectors. This is the foundation for all semantic search, recommendation, and similarity operations across the platform.

**Independent Test**: Deploy the cluster, verify all nodes are running and healthy, confirm the cluster accepts connections on both the high-throughput search port and the admin port, and validate that metrics are being scraped by the monitoring system.

**Acceptance Scenarios**:

1. **Given** a configured environment, **When** the operator deploys with production settings, **Then** 3 nodes start in the designated namespace, all report ready status, and replication is active across nodes.
2. **Given** a configured environment, **When** the operator deploys with development settings, **Then** a single node starts and accepts connections on both API ports.
3. **Given** a running production cluster, **When** one node is terminated, **Then** the remaining nodes continue serving search requests without data loss, and the terminated node rejoins automatically.

---

### User Story 2 - Platform Creates All Required Collections (Priority: P1)

The platform provisions all 4 vector collections with the correct dimensions, distance metric, HNSW index parameters, and payload indexes. Each collection serves a distinct search domain and has independently configured payload indexes to support filtered queries.

**Why this priority**: Collections must exist before any service can store or search vectors. This is required immediately after the cluster is running.

**Independent Test**: After deployment, list all collections and verify each exists with the correct dimension count (configurable, default 768), cosine distance metric, and HNSW parameters. Upsert a test vector to each collection and search it back to confirm end-to-end connectivity.

**Acceptance Scenarios**:

1. **Given** a running cluster, **When** collections are provisioned, **Then** all 4 collections exist with the configured vector dimensions and cosine distance metric.
2. **Given** provisioned collections, **When** a test vector is upserted to any collection, **Then** a nearest-neighbor search returns that vector as the top result.
3. **Given** provisioned collections, **When** listing payload indexes for each collection, **Then** the documented indexes exist and are active (e.g., `workspace_id`, `agent_id`, domain-specific filters).

---

### User Story 3 - Services Upsert and Search Vectors with Payload Filtering (Priority: P1)

Platform services upsert embedding vectors with associated metadata (payload) and search for nearest neighbors with mandatory payload filters. Every search is scoped by `workspace_id` to enforce multi-tenant data isolation. Search results include both the similarity score and the full payload for downstream use.

**Why this priority**: Filtered vector search is the core value proposition. Without it, semantic memory retrieval, agent recommendation, and similarity testing cannot function.

**Independent Test**: Upsert 100 vectors across 3 workspaces with known embeddings. Search with a query vector and `workspace_id` filter — verify results come only from the target workspace, are ranked by similarity, and include payloads.

**Acceptance Scenarios**:

1. **Given** a collection with vectors from multiple workspaces, **When** a service searches with a `workspace_id` filter, **Then** only vectors belonging to that workspace are returned.
2. **Given** a collection with 1000 vectors, **When** a service searches for the 10 nearest neighbors, **Then** results are ranked by descending similarity score and include full payloads.
3. **Given** a collection, **When** a service upserts a vector with a known embedding and then searches with that same embedding, **Then** the upserted vector is returned as the top-1 result with a similarity score of 1.0.
4. **Given** a collection, **When** a service searches with a compound filter (e.g., `workspace_id` AND `lifecycle_state`), **Then** results satisfy both filter conditions.

---

### User Story 4 - Vector Search Responds Within Latency SLA (Priority: P1)

Search queries against collections with up to 1 million vectors complete within 50 milliseconds at p99 when using payload filters. The HNSW index is configured with parameters that balance accuracy and speed for the expected collection sizes.

**Why this priority**: Low-latency search is critical for real-time agent interactions. If search is slow, reasoning loops stall and user experience degrades.

**Independent Test**: Load 1 million random vectors into a collection with payload indexes, run 1000 filtered search queries, measure p99 latency, verify it is under 50ms.

**Acceptance Scenarios**:

1. **Given** a collection with 1 million vectors, **When** 1000 search queries with `workspace_id` filter are executed, **Then** p99 latency is under 50 milliseconds.
2. **Given** a collection with HNSW index parameters configured, **When** recall is measured against a brute-force search, **Then** recall is at least 95% at the configured parameters.

---

### User Story 5 - Operator Backs Up and Restores Vector Data (Priority: P2)

An operator can trigger snapshot-based backups of all collections. Backups are automatically uploaded to the platform's object storage. A scheduled backup runs daily. The operator can restore from any snapshot to recover after data loss or corruption.

**Why this priority**: Backup and restore is essential for operational resilience but not needed for initial deployment or basic search operations.

**Independent Test**: Trigger a snapshot, verify it uploads to object storage. Delete a collection. Restore from the snapshot. Verify all vectors are recovered with correct payloads.

**Acceptance Scenarios**:

1. **Given** a running cluster with data, **When** a snapshot is triggered, **Then** a snapshot file is created and uploaded to the configured object storage bucket within 10 minutes for up to 10 million vectors.
2. **Given** a scheduled backup, **When** the configured time arrives (default: daily at 02:00 UTC), **Then** an automated snapshot is created and uploaded.
3. **Given** a snapshot in object storage, **When** the operator restores from that snapshot, **Then** all collections and their vectors are recovered with correct payloads and indexes.

---

### User Story 6 - Network Access Is Restricted to Authorized Namespaces (Priority: P2)

Only services in authorized namespaces (`platform-control` and `platform-execution`) can connect to the vector search cluster. All other namespaces are blocked by network policy.

**Why this priority**: Security hardening is critical for production but does not block development or basic testing.

**Independent Test**: Attempt to connect to the cluster from an authorized namespace (succeeds) and from an unauthorized namespace (connection refused or times out).

**Acceptance Scenarios**:

1. **Given** a running cluster, **When** a service in `platform-control` connects, **Then** the connection succeeds and the service can upsert and search vectors.
2. **Given** a running cluster, **When** a service in an unauthorized namespace (e.g., `default`) attempts to connect, **Then** the connection is blocked.
3. **Given** a running cluster, **When** the monitoring system scrapes metrics, **Then** the metrics endpoint is accessible from the monitoring namespace.

---

### User Story 7 - All API Requests Require Authentication (Priority: P2)

All vector search API requests (both search and admin ports) require an API key for authentication. The API key is provisioned as a Kubernetes secret and injected into platform services. Requests without a valid API key are rejected.

**Why this priority**: Authentication prevents unauthorized access to vector data but does not block initial development with local testing.

**Independent Test**: Send a search request with a valid API key (succeeds). Send the same request without an API key (rejected with 403). Send with an invalid key (rejected with 403).

**Acceptance Scenarios**:

1. **Given** a running cluster with authentication enabled, **When** a service sends a request with a valid API key, **Then** the request succeeds.
2. **Given** a running cluster with authentication enabled, **When** a request is sent without an API key, **Then** the request is rejected.
3. **Given** a running cluster with authentication enabled, **When** a request is sent with an invalid API key, **Then** the request is rejected.

---

### Edge Cases

- What happens when a collection receives vectors with a dimension count different from the configured dimension? The cluster rejects the upsert with a dimension mismatch error; the calling service must handle the error.
- What happens when a search query uses a payload filter field that has no index? The query succeeds but may be slower (full scan on that field). An alert is raised for missing payload indexes in production.
- What happens when the cluster is under high concurrent load? HNSW search is lock-free and scales with concurrent queries. Write operations may queue during heavy ingestion; the cluster reports backpressure via metrics.
- What happens when a node runs out of disk space? The node stops accepting new data and reports unhealthy. Remaining nodes continue serving search from replicated data. An alert is raised for disk capacity.
- What happens when a snapshot restore is attempted on a running cluster with existing data? The restore operation replaces existing collections with snapshot data. The operator should stop writes during restore to avoid conflicts.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST deploy a vector search cluster with configurable node counts: 3 nodes for production, 1 node for development.
- **FR-002**: System MUST replicate collection data with replication factor 2 in production to survive single-node failures.
- **FR-003**: System MUST create all 4 vector collections with configurable vector dimensions (default: 768) and cosine distance metric.
- **FR-004**: System MUST configure HNSW indexes with tunable parameters (default: ef_construction=128, m=16) on all collections.
- **FR-005**: System MUST create payload indexes on the documented fields for each collection to support filtered queries.
- **FR-006**: System MUST support vector upsert, search, and delete operations via both a high-throughput binary protocol and a REST protocol.
- **FR-007**: System MUST support filtered search with single and compound payload filters (e.g., `workspace_id` AND `lifecycle_state`).
- **FR-008**: System MUST return search results ranked by descending similarity score with full payload included.
- **FR-009**: System MUST enforce API key authentication on all API endpoints.
- **FR-010**: System MUST expose cluster and collection metrics for monitoring (node health, collection size, query latency, disk usage).
- **FR-011**: System MUST enforce network access restrictions so only authorized namespaces can connect.
- **FR-012**: System MUST support snapshot-based backup of all collections.
- **FR-013**: System MUST support automated scheduled backups (configurable schedule, default: daily at 02:00 UTC).
- **FR-014**: System MUST support restore from a snapshot, recovering all collections with vectors, payloads, and indexes.
- **FR-015**: System MUST upload snapshot files to the platform's object storage for durable backup retention.

### Key Entities

- **Vector Search Cluster**: The node ensemble that stores and serves vector data. Defined by node count, replication factor, storage configuration, and authentication settings.
- **Collection**: A named container for vectors of a specific dimension and distance metric. Each collection has an HNSW index, payload indexes, and an independent replication setting.
- **Vector**: A stored embedding with a unique point ID, a float vector of fixed dimension, and an arbitrary JSON payload (metadata).
- **Payload Index**: An index on a specific payload field that enables filtered search without full-scan performance penalty. Configured per-collection.
- **Snapshot**: A point-in-time backup of all collections and their data, stored as a file in object storage. Supports full cluster restore.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 4 collections are created and operational after a single deployment command.
- **SC-002**: The cluster survives termination of any single node without data loss or service interruption for search queries.
- **SC-003**: Filtered search queries against a collection of 1 million vectors complete under 50ms at p99.
- **SC-004**: Search recall is at least 95% compared to brute-force exact search at the configured HNSW parameters.
- **SC-005**: Payload-filtered searches return only vectors matching the filter — zero false positives on `workspace_id` scoping.
- **SC-006**: Automated backup snapshots complete and upload to object storage within 10 minutes for up to 10 million vectors.
- **SC-007**: Restore from snapshot recovers all collections with all vectors, payloads, and indexes intact.
- **SC-008**: Unauthorized namespace connections are blocked 100% of the time by the network policy.
- **SC-009**: API requests without a valid API key are rejected 100% of the time.
- **SC-010**: Cluster metrics (node health, query latency, collection sizes) are visible in the monitoring system within 60 seconds.

## Assumptions

- No dedicated operator (CRD) is required for Qdrant — it is deployed as a standard Kubernetes StatefulSet with a Helm chart. Unlike PostgreSQL (CloudNativePG), Kafka (Strimzi), and MinIO (MinIO Operator), Qdrant has no Kubernetes operator.
- Vector dimensions default to 768 but are configurable per deployment to accommodate different embedding models (e.g., 384 for MiniLM, 1536 for OpenAI text-embedding-3-small).
- HNSW index parameters (`ef_construction=128`, `m=16`) are defaults chosen for a balance of accuracy and speed; they are configurable per collection if needed.
- The platform's Python async client (`qdrant-client 1.12+`) and Go gRPC client are used by producing/searching services but are not part of this feature's scope — this feature covers cluster and collection infrastructure plus the Python client wrapper only.
- Backup snapshots are uploaded to the `backups/qdrant/` prefix in the object storage bucket deployed by feature 004 (minio-object-storage).
- Collection payload indexes are created at provisioning time. Adding new payload indexes after initial deployment is a separate operational task.
- API key authentication is the authentication mechanism; no per-user or per-service RBAC is provided at the cluster level — access control is handled at the network policy layer and by the platform's own authorization middleware.
- Development mode uses a single node with no replication, which means no fault tolerance in development.
