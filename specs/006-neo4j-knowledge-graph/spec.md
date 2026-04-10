# Feature Specification: Neo4j Knowledge Graph Deployment

**Feature Branch**: `006-neo4j-knowledge-graph`
**Created**: 2026-04-09
**Status**: Draft
**Input**: User description: Deploy Neo4j 5.x as the dedicated graph database for knowledge graph queries, memory relationship traversal, workflow dependency analysis, fleet coordination graphs, and discovery evidence provenance chains.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Platform Operator Deploys Graph Database Cluster (Priority: P1)

A platform operator deploys a production-ready graph database cluster with a single command. In production, the cluster runs 3 nodes in a causal cluster configuration (1 leader + 2 followers) for high availability and read scaling. In development, a single standalone instance runs for local testing. The operator can verify cluster health through built-in metrics exposed to the monitoring stack and an admin browser interface.

**Why this priority**: Without the running cluster, no service can store or traverse graph data. This is the foundation for all knowledge graph, provenance, and dependency operations.

**Independent Test**: Deploy the cluster, verify all nodes are running and healthy, confirm the cluster accepts connections on the query protocol port, and validate that the admin interface is accessible.

**Acceptance Scenarios**:

1. **Given** a configured environment, **When** the operator deploys with production settings, **Then** 3 nodes start in the designated namespace, all report ready status, and the cluster forms with one leader and two followers.
2. **Given** a configured environment, **When** the operator deploys with development settings, **Then** a single standalone node starts and accepts connections.
3. **Given** a running production cluster, **When** one follower node is terminated, **Then** the remaining nodes continue serving queries without data loss, and the terminated node rejoins automatically.

---

### User Story 2 - Platform Initializes Schema Constraints and Indexes (Priority: P1)

The platform provisions all required schema constraints (uniqueness on entity IDs) and indexes (workspace scoping, relationship type lookup, evidence-hypothesis linking) through an idempotent initialization process. Constraints and indexes enable efficient queries and enforce data integrity.

**Why this priority**: Schema constraints must exist before any service writes graph data. Without uniqueness constraints, duplicate entities could corrupt the knowledge graph.

**Independent Test**: Run the schema initialization, verify all constraints and indexes exist via the admin interface. Run initialization again to confirm it is idempotent (no errors, no duplicate constraints).

**Acceptance Scenarios**:

1. **Given** a running cluster, **When** schema initialization runs, **Then** all documented uniqueness constraints exist for core entity types (Agent, Workflow, Fleet, Hypothesis, Memory).
2. **Given** initialized schema, **When** initialization runs a second time, **Then** no errors occur and no duplicate constraints or indexes are created.
3. **Given** a uniqueness constraint on Agent.id, **When** a service attempts to create two Agent nodes with the same ID, **Then** the second creation fails with a constraint violation error.

---

### User Story 3 - Services Create and Traverse Graph Relationships (Priority: P1)

Platform services create nodes and relationships in the knowledge graph and traverse them using pattern-matching queries. All queries support workspace scoping to enforce multi-tenant data isolation. Common traversal patterns include: finding all agents related to a workflow, tracing evidence provenance chains for hypotheses, and discovering memory relationships within a workspace.

**Why this priority**: Graph traversal is the core value proposition. Without it, knowledge graph views, provenance chains, and dependency analysis cannot function.

**Independent Test**: Create a graph structure with 5 node types and 10 relationships across 2 workspaces. Query for 3-hop paths within one workspace — verify results contain only nodes from that workspace and correctly follow the relationship chain.

**Acceptance Scenarios**:

1. **Given** a running cluster with schema, **When** a service creates nodes and relationships, **Then** the graph structure is persisted and queryable.
2. **Given** a graph with nodes across multiple workspaces, **When** a service queries with a workspace filter, **Then** only nodes and relationships belonging to that workspace are returned.
3. **Given** a provenance chain (Hypothesis → Evidence → Source), **When** a service traverses the chain up to 3 hops, **Then** the full chain is returned in order with all intermediate nodes.
4. **Given** a graph with 100,000 nodes, **When** a 3-hop traversal query with workspace filter executes, **Then** results are returned within 100 milliseconds.

---

### User Story 4 - Advanced Graph Algorithms Support Complex Queries (Priority: P2)

Platform services use advanced graph algorithms (shortest path, path expansion, neighborhood aggregation) for complex knowledge graph operations like discovering the most connected agents, finding shortest dependency paths in workflows, and computing similarity based on graph structure.

**Why this priority**: Advanced algorithms enhance the knowledge graph but build on top of basic traversal. They are not needed for initial deployment.

**Independent Test**: Load a graph with known shortest paths. Run a shortest-path algorithm between two nodes. Verify the returned path matches the expected shortest route.

**Acceptance Scenarios**:

1. **Given** a graph with multiple paths between two nodes, **When** a service requests the shortest path, **Then** the algorithm returns the path with the fewest hops.
2. **Given** a graph with weighted relationships, **When** a service requests a weighted shortest path, **Then** the algorithm returns the path with the lowest total weight.
3. **Given** a node, **When** a service requests its neighborhood up to depth 2, **Then** all nodes within 2 hops are returned with their relationships.

---

### User Story 5 - Operator Backs Up and Restores Graph Data (Priority: P2)

An operator can trigger database dumps for backup. Dumps are automatically uploaded to the platform's object storage. A scheduled backup runs daily. The operator can restore from any dump to recover after data loss or corruption.

**Why this priority**: Backup and restore is essential for operational resilience but not needed for initial deployment.

**Independent Test**: Create test data, trigger a dump, verify it uploads to object storage. Destroy the database. Restore from the dump. Verify all nodes and relationships are recovered.

**Acceptance Scenarios**:

1. **Given** a running cluster with data, **When** a dump is triggered, **Then** a dump file is created and uploaded to the configured object storage location within 15 minutes for up to 10 million nodes.
2. **Given** a scheduled backup, **When** the configured time arrives (default: daily at 03:00 UTC), **Then** an automated dump is created and uploaded.
3. **Given** a dump file in object storage, **When** the operator restores from that dump, **Then** all nodes, relationships, constraints, and indexes are recovered.

---

### User Story 6 - Network Access Is Restricted to Authorized Namespaces (Priority: P2)

Only services in authorized namespaces (`platform-control` and `platform-execution`) can connect to the graph database. All other namespaces are blocked by network policy.

**Why this priority**: Security hardening is critical for production but does not block development or basic testing.

**Independent Test**: Attempt to connect from an authorized namespace (succeeds) and from an unauthorized namespace (connection refused or times out).

**Acceptance Scenarios**:

1. **Given** a running cluster, **When** a service in `platform-control` connects, **Then** the connection succeeds and the service can execute queries.
2. **Given** a running cluster, **When** a service in an unauthorized namespace (e.g., `default`) attempts to connect, **Then** the connection is blocked.
3. **Given** a running cluster, **When** the monitoring system scrapes metrics, **Then** the metrics endpoint is accessible from the monitoring namespace.

---

### User Story 7 - Local Mode Falls Back to Simplified Graph Queries (Priority: P2)

When the platform runs in local mode without a graph database, graph queries fall back to a simplified recursive query mechanism against the relational database. This fallback supports up to 3-hop traversals with degraded performance. Services detect which mode is active through configuration and adapt their query strategy automatically.

**Why this priority**: Local mode support enables development without requiring a graph database cluster, but is not needed for production deployment.

**Independent Test**: Configure the platform in local mode (no graph database URL). Execute a 3-hop traversal query. Verify results are correct (same structure as graph database results, though potentially slower).

**Acceptance Scenarios**:

1. **Given** the platform in local mode, **When** a service executes a graph query, **Then** results are returned using the recursive fallback mechanism.
2. **Given** local mode, **When** a 3-hop traversal is requested, **Then** results are returned correctly within 5 seconds (degraded but functional).
3. **Given** local mode, **When** a query exceeding 3 hops is requested, **Then** the service returns a clear error indicating the hop limit for local mode.

---

### Edge Cases

- What happens when a node is deleted that has existing relationships? The delete operation must explicitly delete relationships first or use a detach-delete pattern. The system returns an error if a node deletion would leave dangling relationships without using detach-delete.
- What happens when a relationship is created between nodes in different workspaces? The system allows cross-workspace relationships but tags them with both workspace IDs. Queries filtered by a single workspace will not return cross-workspace relationships unless explicitly requested.
- What happens when the cluster leader goes down? The followers automatically elect a new leader. Write operations are briefly unavailable during leader election (typically < 10 seconds). Read operations continue on followers.
- What happens when a query traverses a cycle in the graph? The query engine handles cycles natively — traversal stops when a previously visited node is encountered. No infinite loops occur.
- What happens when a constraint creation fails due to existing duplicate data? The constraint creation returns an error listing the duplicate values. The operator must resolve duplicates before the constraint can be applied.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST deploy a graph database cluster with configurable node counts: 3-node causal cluster for production, 1 standalone node for development.
- **FR-002**: System MUST replicate data across cluster nodes in production for fault tolerance during single-node failures.
- **FR-003**: System MUST create all documented uniqueness constraints on core entity ID fields (Agent, Workflow, Fleet, Hypothesis, Memory).
- **FR-004**: System MUST create performance indexes on workspace scoping fields, evidence-hypothesis linking, and relationship type lookups.
- **FR-005**: System MUST support node creation, relationship creation, and pattern-matching traversal queries via the binary query protocol.
- **FR-006**: System MUST support workspace-scoped queries that filter results to a single tenant's data.
- **FR-007**: System MUST support multi-hop traversal queries (minimum 3 hops) with configurable depth.
- **FR-008**: System MUST include advanced graph algorithm capabilities (shortest path, path expansion, neighborhood aggregation).
- **FR-009**: System MUST authenticate all connections with platform-managed credentials.
- **FR-010**: System MUST expose cluster and query metrics for monitoring (node health, query latency, active transactions, storage usage).
- **FR-011**: System MUST enforce network access restrictions so only authorized namespaces can connect.
- **FR-012**: System MUST support database dump-based backup of all graph data.
- **FR-013**: System MUST support automated scheduled backups (configurable schedule, default: daily at 03:00 UTC).
- **FR-014**: System MUST support restore from a dump, recovering all nodes, relationships, constraints, and indexes.
- **FR-015**: System MUST upload dump files to the platform's object storage for durable backup retention.
- **FR-016**: System MUST provide a fallback query mechanism for local mode that supports up to 3-hop traversals against the relational database.
- **FR-017**: System MUST provide an admin browser interface for operators to inspect graph data, run ad-hoc queries, and view cluster status.

### Key Entities

- **Graph Database Cluster**: The node ensemble that stores and serves graph data. Defined by node count, cluster role assignment (leader/follower), storage configuration, and authentication.
- **Node (Graph)**: A labeled entity in the graph (e.g., Agent, Workflow, Fleet, Hypothesis, Memory, Evidence). Has properties including a unique ID and workspace_id.
- **Relationship**: A typed, directed connection between two nodes (e.g., DEPENDS_ON, PRODUCED_BY, RELATES_TO). May have properties including weight and metadata.
- **Constraint**: A schema rule enforcing data integrity (e.g., unique ID per label). Applied at the cluster level.
- **Index**: A performance optimization for frequently queried properties (e.g., workspace_id, hypothesis_id). Applied per label or relationship type.
- **Dump**: A full database export file for backup and restore. Includes all nodes, relationships, constraints, indexes, and configuration.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All documented constraints (5 uniqueness) and indexes (3 performance) are created and active after a single initialization command.
- **SC-002**: The cluster survives termination of any single node without data loss or query service interruption for read operations.
- **SC-003**: 3-hop traversal queries with workspace filter complete under 100ms at p99 for graphs with up to 1 million nodes.
- **SC-004**: Advanced graph algorithms (shortest path) complete under 500ms for graphs with up to 1 million nodes.
- **SC-005**: Workspace-scoped queries return zero nodes from other workspaces — 100% tenant isolation.
- **SC-006**: Automated backup dumps complete and upload to object storage within 15 minutes for up to 10 million nodes.
- **SC-007**: Restore from dump recovers all nodes, relationships, constraints, and indexes with zero data loss.
- **SC-008**: Unauthorized namespace connections are blocked 100% of the time by the network policy.
- **SC-009**: Local mode fallback correctly handles 3-hop traversals with results matching graph database output structure.
- **SC-010**: Cluster metrics (node health, query latency, active transactions) are visible in the monitoring system within 60 seconds.

## Assumptions

- No dedicated Kubernetes operator is used for the graph database — it is deployed as a standard Kubernetes StatefulSet with a Helm chart, similar to the Qdrant deployment pattern (feature 005).
- The APOC plugin is pre-installed in the container image or installed via plugin configuration in the StatefulSet; it provides advanced graph algorithms (shortest path, path expansion).
- The platform's Python async client (`neo4j-python-driver 5.x`, async driver `AsyncGraphDatabase`) is used by platform services but the full client wrapper is not part of this feature's scope — this feature covers cluster and schema infrastructure plus a basic Python client wrapper.
- Backup dumps are uploaded to the `backups/neo4j/` prefix in the object storage bucket deployed by feature 004 (minio-object-storage).
- Schema constraints and indexes are created via an idempotent initialization script using `IF NOT EXISTS` syntax (available in Neo4j 5.x+).
- The local mode fallback uses SQLAlchemy recursive CTEs against PostgreSQL (feature 001), not a separate graph database. Performance is degraded (seconds vs. milliseconds) and maximum traversal depth is limited to 3 hops.
- Development mode uses the Community Edition (single node, no clustering). Production uses the Enterprise Edition or a clustering-capable configuration.
- Cross-workspace relationships are allowed but require explicit opt-in in queries — default workspace-scoped queries exclude them.
