# Feature Specification: OpenSearch Full-Text Search Deployment

**Feature Branch**: `008-opensearch-full-text-search`
**Created**: 2026-04-10
**Status**: Draft
**Input**: User description: Deploy OpenSearch 2.x as the dedicated full-text search engine for marketplace agent discovery, natural-language search, faceted filtering, hierarchical taxonomy navigation, audit log search, and operator diagnostic queries.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Platform Operator Deploys Search Engine Cluster (Priority: P1)

A platform operator deploys a production-ready full-text search cluster with a single command. In production, the cluster runs 3 nodes (1 dedicated master-eligible, 2 data nodes) for high availability and search distribution. In development, a single standalone node runs for local testing. The operator can verify cluster health through built-in metrics exposed to the monitoring stack and an operator dashboard for ad-hoc search and index inspection.

**Why this priority**: Without the running cluster, no service can index or search any data. This is the foundation for marketplace discovery, audit search, and all text-based query operations.

**Independent Test**: Deploy the cluster, verify all nodes are running with green cluster health, confirm the cluster accepts index and search requests, and validate that the operator dashboard is accessible.

**Acceptance Scenarios**:

1. **Given** a configured environment, **When** the operator deploys with production settings, **Then** 3 nodes start in the designated namespace, the cluster reports green health status, and the operator dashboard is accessible.
2. **Given** a configured environment, **When** the operator deploys with development settings, **Then** a single standalone node starts, accepts connections, and reports green health with yellow index status (expected for single-node with replicas configured).
3. **Given** a running production cluster, **When** one data node is terminated, **Then** the remaining nodes continue serving search queries, replica shards promote to primary, and the terminated node rejoins automatically.

---

### User Story 2 - Platform Initializes Index Templates and Mappings (Priority: P1)

The platform provisions all required index templates (marketplace agents, audit events, connector payloads) with their field mappings, custom analyzers (including synonym expansion), and index lifecycle management policies through an idempotent initialization process. Templates ensure that newly created indexes automatically inherit the correct mappings and settings.

**Why this priority**: Index templates must exist before any service can index documents. Without them, documents would be indexed with auto-detected mappings, leading to incorrect field types and missing analysis features.

**Independent Test**: Run the template initialization, verify all templates exist and are correctly configured. Create a test index matching a template pattern — verify it inherits the expected mappings and analyzer settings. Run initialization again to confirm it is idempotent.

**Acceptance Scenarios**:

1. **Given** a running cluster, **When** template initialization runs, **Then** all documented index templates exist (`marketplace-agents`, `audit-events`, `connector-payloads`) with correct field mappings and analyzer configurations.
2. **Given** initialized templates, **When** initialization runs a second time, **Then** no errors occur and no duplicate templates are created.
3. **Given** the `marketplace-agents` template, **When** a new index matching the template pattern is created, **Then** it automatically inherits the custom analyzer with synonym expansion and all mapped fields.
4. **Given** the `audit-events` template, **When** it is created, **Then** it includes an index lifecycle management policy for data retention.

---

### User Story 3 - Services Index and Search Marketplace Agents (Priority: P1)

Platform services index agent profiles into the search engine and search them using natural-language queries, filters, and faceted aggregations. Search queries return relevance-ranked results using BM25 scoring with synonym expansion (e.g., searching "summarizer" also matches agents described as "text summary agent"). All queries support workspace scoping to enforce multi-tenant data isolation.

**Why this priority**: Marketplace search is the primary user-facing search feature. Without it, users cannot discover agents through natural language or browse by capability.

**Independent Test**: Index 50 agent profiles across 3 workspaces with varied descriptions, tags, and capabilities. Search with a natural-language query — verify results are relevance-ranked. Apply workspace filter — verify only matching agents returned. Run faceted aggregation — verify correct counts by capability and maturity level.

**Acceptance Scenarios**:

1. **Given** indexed agent profiles, **When** a service searches with a natural-language query (e.g., "agent that summarizes text"), **Then** results are returned ranked by relevance with the most relevant agents first.
2. **Given** a synonym dictionary mapping "summarizer" to "text summary agent", **When** a user searches for "summarizer", **Then** agents described as "text summary agent" appear in results.
3. **Given** agents across multiple workspaces, **When** a service searches with a workspace filter, **Then** only agents belonging to that workspace are returned.
4. **Given** indexed agents with varied capabilities and maturity levels, **When** a service requests faceted aggregations, **Then** correct counts are returned for each capability value and maturity level.
5. **Given** 100,000 indexed agent profiles, **When** a search query with filters executes, **Then** results are returned within 200 milliseconds.

---

### User Story 4 - Services Index and Search Audit Events (Priority: P2)

Platform services index audit events (security actions, resource modifications, administrative operations) and search them by event type, actor, time range, workspace, and free-text details. Audit search supports compliance investigations and forensic analysis.

**Why this priority**: Audit search is important for compliance and security but builds on the same infrastructure as marketplace search. Not needed for initial marketplace deployment.

**Independent Test**: Index 1000 audit events across 5 workspaces and 10 event types. Search by event type and time range — verify correct results. Search by free-text details — verify relevance ranking.

**Acceptance Scenarios**:

1. **Given** indexed audit events, **When** a service searches by event type and time range, **Then** only matching events are returned in chronological order.
2. **Given** indexed audit events with text details, **When** a service searches by free-text query, **Then** results are returned ranked by relevance.
3. **Given** audit events across workspaces, **When** a service searches with a workspace filter, **Then** only events from that workspace are returned.

---

### User Story 5 - Index Lifecycle Management Automatically Manages Data Retention (Priority: P2)

Indexes with lifecycle policies are automatically managed. Audit event indexes roll over based on size or age and are deleted after the configured retention period. Connector payload indexes are deleted after 30 days. Marketplace agent indexes have no lifecycle policy (retained indefinitely, updated in place).

**Why this priority**: Lifecycle management prevents unbounded storage growth for high-volume indexes (audit events, connector payloads) but is not needed for initial deployment.

**Independent Test**: Create an index with a lifecycle policy configured for short retention (e.g., 1 minute). Verify the index is deleted after the retention period elapses.

**Acceptance Scenarios**:

1. **Given** an audit event index with a retention policy, **When** the index exceeds the configured age, **Then** the lifecycle policy transitions the index to deletion.
2. **Given** a connector payload index with a 30-day lifecycle, **When** data older than 30 days exists, **Then** the lifecycle policy deletes the expired index.
3. **Given** a marketplace agent index with no lifecycle policy, **When** data of any age exists, **Then** the data is retained indefinitely.

---

### User Story 6 - Operator Backs Up and Restores Search Indexes (Priority: P2)

An operator can register a snapshot repository backed by the platform's object storage. Snapshots of all indexes can be triggered manually or run on a daily schedule. The operator can restore from any snapshot to recover after data loss or index corruption.

**Why this priority**: Backup and restore is essential for operational resilience but not needed for initial deployment.

**Independent Test**: Create test data, register a snapshot repository, trigger a snapshot. Verify snapshot completes. Delete an index. Restore from snapshot. Verify all documents are recovered.

**Acceptance Scenarios**:

1. **Given** a running cluster with indexed data, **When** a snapshot is triggered, **Then** the snapshot completes and is stored in the configured object storage location within 15 minutes for up to 10 million documents.
2. **Given** a scheduled snapshot, **When** the configured time arrives (default: daily at 05:00 UTC), **Then** an automated snapshot is created.
3. **Given** a snapshot in object storage, **When** the operator restores from that snapshot, **Then** all indexes, documents, mappings, and settings are recovered.

---

### User Story 7 - Network Access Is Restricted to Authorized Namespaces (Priority: P2)

Only services in authorized namespaces (`platform-control` and `platform-execution`) can connect to the search engine. All other namespaces are blocked by network policy. The monitoring system can scrape metrics from the designated monitoring namespace. The operator dashboard is accessible from the operations namespace.

**Why this priority**: Security hardening is critical for production but does not block development or basic testing.

**Independent Test**: Attempt to connect from an authorized namespace (succeeds) and from an unauthorized namespace (connection refused or times out).

**Acceptance Scenarios**:

1. **Given** a running cluster, **When** a service in `platform-control` connects via the REST interface, **Then** the connection succeeds and the service can execute search queries.
2. **Given** a running cluster, **When** a service in an unauthorized namespace (e.g., `default`) attempts to connect, **Then** the connection is blocked.
3. **Given** a running cluster, **When** the monitoring system scrapes metrics, **Then** the metrics endpoint is accessible from the monitoring namespace.

---

### User Story 8 - Synonym Dictionary Is Extensible by Administrators (Priority: P2)

Administrators can update the synonym dictionary to add new synonyms or modify existing ones. Updated synonyms take effect after an index refresh or reindex operation. The initial synonym set covers common agent type mappings (summarizer, translator, classifier and their variations).

**Why this priority**: Extensible synonyms improve search quality over time but the initial dictionary covers the most important terms. Not needed for initial deployment.

**Independent Test**: Add a new synonym mapping. Reindex a test agent. Search using the new synonym — verify the agent appears in results.

**Acceptance Scenarios**:

1. **Given** an initial synonym dictionary, **When** an administrator adds a new synonym mapping, **Then** the dictionary is updated successfully.
2. **Given** an updated synonym dictionary, **When** an index refresh or reindex occurs, **Then** new searches use the updated synonyms.
3. **Given** the initial synonym dictionary, **When** a user searches for "summarizer", **Then** agents described as "text summary agent" or "summarization" appear in results.

---

### Edge Cases

- What happens when a document is indexed with fields not in the mapping? The search engine uses dynamic mapping to auto-detect field types for unmapped fields. This is permitted for flexibility but auto-detected fields do not benefit from custom analyzers. The platform client should log a warning when indexing documents with unmapped fields.
- What happens when a synonym creates a circular reference? The search engine's synonym filter handles circular references gracefully — each synonym expands once, preventing infinite loops. The synonym dictionary should be validated at update time to warn administrators about potential circular references.
- What happens when all master-eligible nodes go down? The cluster becomes read-only (search still works on data nodes for cached queries) but cannot accept new index operations or cluster state changes. On recovery, the master-eligible node re-forms the cluster. Monitoring alerts trigger when the cluster health is red.
- What happens when a search query matches millions of results? The search engine paginates results using the `from` + `size` parameters for shallow pagination and the `search_after` cursor for deep pagination. The platform client enforces a maximum `size` of 10,000 per page (OpenSearch default limit).
- What happens when an ILM policy triggers during an active search? The search engine handles this gracefully — active search contexts maintain references to the segments they're reading. Index deletion only removes segments after all active readers release them.
- What happens when the synonym dictionary file is malformed? The index creation or update fails with a clear error message indicating the malformed synonym entry. The existing index continues to use the previous valid synonym set until the fix is applied.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST deploy a search cluster with configurable topology: 3 nodes (1 master-eligible + 2 data) for production, 1 standalone node for development.
- **FR-002**: System MUST distribute and replicate index shards across cluster nodes in production for fault tolerance during single-node failures.
- **FR-003**: System MUST create all documented index templates (`marketplace-agents`, `audit-events`, `connector-payloads`) with correct field mappings, analyzers, and settings.
- **FR-004**: System MUST configure a custom text analyzer with synonym expansion for the marketplace agents index, supporting an extensible synonym dictionary.
- **FR-005**: System MUST support full-text search with BM25 relevance scoring across all indexed document types.
- **FR-006**: System MUST support workspace-scoped queries that filter results to a single tenant's data.
- **FR-007**: System MUST support faceted aggregations on keyword fields (capabilities, maturity level, trust score ranges, lifecycle state, certification status).
- **FR-008**: System MUST configure index lifecycle management policies for audit event and connector payload indexes with configurable retention periods.
- **FR-009**: System MUST authenticate all connections with platform-managed credentials.
- **FR-010**: System MUST expose cluster and search metrics for monitoring (cluster health, search latency, indexing rate, JVM usage, disk usage).
- **FR-011**: System MUST enforce network access restrictions so only authorized namespaces can connect.
- **FR-012**: System MUST support snapshot-based backup of all indexes to the platform's object storage.
- **FR-013**: System MUST support automated scheduled snapshots (configurable schedule, default: daily at 05:00 UTC).
- **FR-014**: System MUST support restore from snapshot, recovering all indexes, documents, mappings, and settings.
- **FR-015**: System MUST provide an operator dashboard for ad-hoc search, index inspection, and cluster monitoring.
- **FR-016**: System MUST support multilingual text analysis for agent descriptions in the marketplace index.
- **FR-017**: System MUST support deep pagination using cursor-based pagination for result sets exceeding the maximum page size.

### Key Entities

- **Search Cluster**: The node ensemble that stores and serves search data. Defined by node count, node roles (master-eligible, data), storage configuration, and authentication.
- **Index Template**: A pre-defined mapping and settings configuration that is automatically applied to new indexes matching a name pattern. Includes field mappings, analyzers, and lifecycle policies.
- **Marketplace Agent Document**: A searchable representation of an agent profile. Fields include name, purpose, description, tags, capabilities, maturity level, trust score, workspace, lifecycle state, and certification status.
- **Audit Event Document**: A searchable record of a security or administrative action. Fields include event type, actor, timestamp, workspace, resource type, action, and free-text details.
- **Connector Payload Document**: A searchable record of connector input/output. Fields include connector type, workspace, timestamp, payload text, and direction.
- **Synonym Dictionary**: A mapping of equivalent terms used to expand search queries (e.g., "summarizer" → "text summary agent"). Extensible by administrators.
- **Index Lifecycle Policy**: A rule governing index rollover, retention, and deletion based on age or size thresholds.
- **Snapshot**: A point-in-time backup of all indexes stored in object storage for recovery.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All documented index templates (3) are created and active after a single initialization command.
- **SC-002**: The cluster survives termination of any single node without search service interruption.
- **SC-003**: Natural-language search queries return relevant results — synonym-expanded queries (e.g., "summarizer") match expected agent descriptions in the top 10 results.
- **SC-004**: Search queries with filters complete under 200 milliseconds at p99 for indexes with up to 100,000 documents.
- **SC-005**: Faceted aggregations return correct counts for all configured facet fields — zero discrepancy with manual count.
- **SC-006**: Workspace-scoped queries return zero documents from other workspaces — 100% tenant isolation.
- **SC-007**: Index lifecycle policies delete expired indexes within 24 hours of the configured retention threshold.
- **SC-008**: Automated snapshot completes and uploads to object storage within 15 minutes for up to 10 million documents.
- **SC-009**: Restore from snapshot recovers all indexes, documents, and mappings with zero document loss.
- **SC-010**: Unauthorized namespace connections are blocked 100% of the time by the network policy.
- **SC-011**: Cluster metrics (health, search latency, indexing rate, JVM usage) are visible in the monitoring system within 60 seconds.

## Assumptions

- No dedicated Kubernetes operator is used for the search engine — it is deployed as a standard Kubernetes StatefulSet with a Helm chart, similar to the Qdrant (feature 005), Neo4j (feature 006), and ClickHouse (feature 007) deployment patterns.
- The security plugin is enabled with an internal user database (not external LDAP or SAML). A single admin user is provisioned via Kubernetes Secret for platform services.
- The ICU analysis plugin is pre-installed in the container image or installed via plugin configuration for multilingual text support.
- The platform's Python async client (`opensearch-py 2.x`, async client) is used by platform services but the full client wrapper is not part of this feature's scope — this feature covers cluster and index infrastructure plus a basic Python client wrapper.
- Snapshot data is uploaded to the `backups/opensearch/` prefix in the object storage bucket deployed by feature 004 (minio-object-storage).
- Index template initialization uses the PUT template API with `_template` or `_index_template` endpoint — existing templates are updated in place (idempotent).
- Data flows into the search engine from the projection-indexer runtime profile (bounded context: `search/`) — but the indexer integration is not part of this feature's scope. This feature provides the schema and client; the projection-indexer is implemented in a downstream feature.
- Development mode runs a single node with security plugin disabled for ease of local testing. Production mode enables the security plugin.
- The operator dashboard is deployed as a separate lightweight deployment (not part of the search cluster StatefulSet) — it connects to the search cluster as a client.
- Synonym dictionaries are stored as files in the container image or mounted via ConfigMap. Updates require an index close/open or reindex operation to take effect.
