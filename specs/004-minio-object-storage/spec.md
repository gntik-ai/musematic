# Feature Specification: S3-Compatible Object Storage Deployment

**Feature Branch**: `004-minio-object-storage`
**Created**: 2026-04-09
**Status**: Draft
**Input**: User description: Deploy MinIO as the S3-compatible object storage for agent packages, execution artifacts, reasoning traces, evidence bundles, simulation artifacts, and backup storage.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Platform Operator Deploys Object Storage Cluster (Priority: P1)

A platform operator deploys production-ready object storage with a single command. In production, the cluster runs 4 storage nodes with erasure coding for data durability. In development, a single storage node runs in filesystem mode for local testing. The operator can verify cluster health through the management console and built-in metrics exposed to the monitoring stack.

**Why this priority**: Without the running storage cluster, no service can store or retrieve artifacts. This is the foundation for all artifact and backup operations across the platform.

**Independent Test**: Deploy the cluster, verify all storage nodes are running and healthy, confirm the S3 API accepts connections on the designated port, and validate that the management console is accessible.

**Acceptance Scenarios**:

1. **Given** a configured environment, **When** the operator deploys with production settings, **Then** 4 storage nodes start in the designated namespace, all report ready status, and the cluster forms with erasure coding protection.
2. **Given** a configured environment, **When** the operator deploys with development settings, **Then** a single storage node starts in filesystem mode and accepts S3 API connections.
3. **Given** a running production cluster, **When** one storage node is terminated, **Then** the remaining nodes continue serving requests without data loss, and the terminated node rejoins automatically.

---

### User Story 2 - Platform Creates All Required Buckets with Lifecycle Policies (Priority: P1)

The platform provisions all 8 storage buckets with the correct lifecycle (retention) policies after a single deployment. Each bucket serves a distinct purpose and has an independently configured retention period. Buckets that store immutable records (agent packages, evidence) retain data indefinitely, while transient data buckets automatically expire old objects.

**Why this priority**: Buckets must exist before any service can store or retrieve objects. This is required immediately after the cluster is running.

**Independent Test**: After deployment, list all buckets and verify each exists with the correct lifecycle configuration. Upload a test object to each bucket and retrieve it to confirm end-to-end connectivity.

**Acceptance Scenarios**:

1. **Given** a running storage cluster, **When** buckets are provisioned, **Then** all 8 buckets exist with their documented lifecycle policies (indefinite, 30d, or 90d).
2. **Given** provisioned buckets, **When** a test object is uploaded to any bucket, **Then** it can be retrieved with identical content.
3. **Given** a bucket with a 30-day lifecycle policy, **When** an object is older than 30 days, **Then** it is automatically deleted by the lifecycle rule.

---

### User Story 3 - Services Store and Retrieve Objects via S3 API (Priority: P1)

Platform services upload and download objects using standard S3 API operations (PUT, GET, DELETE, LIST). Objects can range from small metadata files to large multi-gigabyte artifacts. Large uploads (over 100 MB) use multipart upload for reliability. All operations authenticate with service credentials.

**Why this priority**: Basic S3 operations are the core value proposition of the object storage. Without them, no artifact workflow can function.

**Independent Test**: Upload a small file (1 KB), a medium file (10 MB), and a large file (1 GB) to a bucket. Retrieve each, verify content integrity via checksum. Delete each, verify it no longer exists.

**Acceptance Scenarios**:

1. **Given** a running bucket, **When** a service uploads an object, **Then** the object is stored and retrievable with identical content (verified by checksum).
2. **Given** a large object (>100 MB), **When** a service uploads using multipart upload, **Then** the upload completes successfully and the object is retrievable as a single unit.
3. **Given** a stored object, **When** a service deletes it, **Then** it is no longer retrievable.
4. **Given** a bucket with multiple objects, **When** a service lists objects with a prefix filter, **Then** only matching objects are returned.

---

### User Story 4 - Agent Package Versioning Preserves All Revisions (Priority: P2)

The agent-packages bucket has versioning enabled so every upload of an agent package preserves previous versions. Operators can list all versions of a package and retrieve any specific version. Versioning supports immutable revision history required for agent lifecycle auditing.

**Why this priority**: Versioning supports the immutable revision audit trail but is not needed for initial deployment or basic operations.

**Independent Test**: Upload an object with a known key, upload a different object with the same key, list versions, verify both versions exist and are independently retrievable with correct content.

**Acceptance Scenarios**:

1. **Given** a versioned bucket, **When** an object is uploaded twice with the same key, **Then** both versions are retained and independently retrievable.
2. **Given** a versioned bucket with multiple object versions, **When** an operator lists versions for a key, **Then** all versions are returned with timestamps and version identifiers.
3. **Given** a specific version identifier, **When** a service requests that version, **Then** the exact content of that version is returned regardless of subsequent uploads.

---

### User Story 5 - Simulation Artifacts Are Isolated from Production (Priority: P2)

Simulation artifacts are stored in a dedicated bucket (`simulation-artifacts`) that is physically and logically separate from production artifact buckets. Services in the simulation namespace can write only to the simulation bucket. This ensures no simulation data contaminates production storage.

**Why this priority**: Isolation is a security and governance requirement critical for production trust but does not block development or basic storage testing.

**Independent Test**: Upload an artifact to the simulation bucket from the simulation namespace (succeeds). Attempt to write to a production bucket from the simulation namespace (blocked by policy). Verify no simulation objects appear in production bucket listings.

**Acceptance Scenarios**:

1. **Given** a running storage cluster, **When** a simulation service writes to `simulation-artifacts`, **Then** the object is stored successfully.
2. **Given** separate production and simulation buckets, **When** listing objects in any production bucket, **Then** no simulation artifacts appear.
3. **Given** the `simulation-artifacts` bucket, **When** a lifecycle rule expires objects older than 30 days, **Then** expired simulation artifacts are deleted without affecting production buckets.

---

### User Story 6 - Network Access Is Restricted to Authorized Namespaces (Priority: P2)

Only services in authorized namespaces (`platform-control`, `platform-execution`, and `platform-simulation` for simulation bucket only) can connect to the storage API. All other namespaces are blocked by network policy.

**Why this priority**: Security hardening is critical for production but does not block development or basic testing.

**Independent Test**: Attempt to connect to the S3 API from an authorized namespace (succeeds) and from an unauthorized namespace (connection refused or times out).

**Acceptance Scenarios**:

1. **Given** a running storage cluster, **When** a service in `platform-control` connects, **Then** the connection succeeds and the service can upload/download objects.
2. **Given** a running storage cluster, **When** a service in an unauthorized namespace (e.g., `default`) attempts to connect, **Then** the connection is blocked.
3. **Given** the `simulation-artifacts` bucket, **When** a service in `platform-simulation` connects, **Then** it can access only the simulation bucket.

---

### User Story 7 - Operator Monitors Storage Health and Usage (Priority: P2)

Operators can monitor storage cluster health, disk usage, request rates, and error rates through the monitoring stack. The management console provides a visual interface for bucket browsing, object inspection, and cluster status. Metrics are scraped by the monitoring system within 60 seconds of metric changes.

**Why this priority**: Observability is important for production operations but not needed for initial deployment and basic functionality.

**Independent Test**: Access the management console, verify it shows cluster status, bucket list, and object counts. Check that storage metrics appear in the monitoring system.

**Acceptance Scenarios**:

1. **Given** a running cluster, **When** the operator accesses the management console, **Then** cluster status, all 8 buckets, and per-bucket object counts are visible.
2. **Given** a running cluster, **When** storage metrics are scraped, **Then** disk usage, request counts, and error rates appear in the monitoring system within 60 seconds.
3. **Given** a storage operation (upload or download), **When** the operation completes, **Then** the corresponding metric counter increments in the monitoring system.

---

### Edge Cases

- What happens when a storage node runs out of disk space? Erasure coding allows the cluster to continue operating on remaining nodes; an alert is raised for disk capacity. New writes fail if all nodes are full.
- What happens when a service attempts to upload to a non-existent bucket? The S3 API returns a `NoSuchBucket` error; the calling service must handle the error. Buckets are not auto-created.
- What happens when a multipart upload is interrupted? Incomplete multipart uploads remain as fragments. A lifecycle policy automatically cleans up incomplete multipart uploads after 7 days to reclaim storage.
- What happens when a versioned object is deleted? A delete marker is placed; the object is hidden from normal GET/LIST but previous versions remain accessible. Permanent deletion requires explicit version-targeted DELETE.
- What happens when the management console is inaccessible? S3 API operations continue unaffected — the console is a separate component. An alert is raised for console unavailability.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST deploy an object storage cluster that provides an S3-compatible API.
- **FR-002**: System MUST support configurable cluster sizes: 4 nodes with erasure coding for production, 1 node in filesystem mode for development.
- **FR-003**: System MUST create all 8 storage buckets with their respective lifecycle (retention) policies.
- **FR-004**: System MUST support standard S3 operations: PUT, GET, DELETE, LIST, HEAD on all buckets.
- **FR-005**: System MUST support multipart upload for objects larger than 100 MB, completing uploads of at least 1 GB.
- **FR-006**: System MUST enable versioning on the `agent-packages` bucket to preserve all object revisions.
- **FR-007**: System MUST enforce lifecycle policies that automatically delete expired objects (30-day and 90-day buckets).
- **FR-008**: System MUST clean up incomplete multipart uploads after 7 days via lifecycle rule.
- **FR-009**: System MUST provide a management console accessible to operators for cluster and bucket inspection.
- **FR-010**: System MUST expose cluster and bucket metrics for monitoring (disk usage, request rates, error rates, object counts).
- **FR-011**: System MUST enforce network access restrictions so only authorized namespaces can connect to the S3 API.
- **FR-012**: System MUST isolate the simulation-artifacts bucket from production buckets at the access-policy level.
- **FR-013**: System MUST authenticate all S3 API requests with service credentials (access key and secret key).
- **FR-014**: System MUST survive single-node failure in production without data loss or service interruption.
- **FR-015**: System MUST support the `evidence-bundles` bucket with indefinite retention for compliance artifacts.

### Key Entities

- **Storage Cluster**: The node ensemble that stores and serves object data. Defined by node count, storage configuration, and data protection mode (erasure coding or filesystem).
- **Bucket**: A named storage container with an independently configured lifecycle policy. Each bucket has a purpose, retention period, and optional versioning setting.
- **Object**: A stored blob identified by bucket name + key. Has content, metadata (content-type, custom headers), checksum, and optionally multiple versions.
- **Lifecycle Policy**: An automated rule that deletes objects older than a configured retention period. Applies per-bucket. Also handles incomplete multipart upload cleanup.
- **Service Credentials**: Access key + secret key pair used to authenticate S3 API requests. Managed as Kubernetes secrets and injected into service pods.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 8 storage buckets are created and operational after a single deployment command.
- **SC-002**: The cluster survives termination of any single node without data loss or service interruption for clients.
- **SC-003**: Objects up to 1 GB in size can be uploaded via multipart upload and fully retrieved with matching checksums.
- **SC-004**: Lifecycle policies delete expired objects within 24 hours of expiration across all time-limited buckets.
- **SC-005**: Object upload and download latency is under 200ms at p99 for objects under 1 MB within the same data center.
- **SC-006**: The management console is accessible to operators and displays cluster status, all 8 buckets, and per-bucket metrics.
- **SC-007**: Unauthorized namespace connections are blocked 100% of the time by the network policy.
- **SC-008**: The `agent-packages` bucket retains all object versions — no version is lost after overwrite or delete.
- **SC-009**: No simulation artifacts appear in any production bucket listing, and no production artifacts appear in the simulation bucket.
- **SC-010**: Storage metrics (disk usage, request rates, error rates) are visible in the monitoring system within 60 seconds of metric changes.

## Assumptions

- The storage operator is pre-installed in the target environment before this feature is deployed. This feature deploys cluster and bucket resources, not the operator itself.
- All services that upload or download objects implement their own serialization/deserialization logic; the storage system stores opaque byte payloads.
- Service credentials (access key + secret key) are provisioned as Kubernetes secrets by this feature and consumed by platform services via environment variable injection.
- The `simulation-artifacts` bucket follows the same infrastructure pattern as all other buckets; the isolation between simulation and production is enforced by access policies (separate credentials or bucket policies), not by separate storage clusters.
- Development mode uses a single node with no erasure coding, which means no fault tolerance in development.
- Disk-based persistent storage is available in the deployment environment for storage node data directories.
- The platform's Python async client (`aioboto3`) and Go client (`aws-sdk-go-v2`) are used by producing/consuming services but are not part of this feature's scope — this feature covers cluster and bucket infrastructure plus the Python client wrapper only.
- Lifecycle policy execution timing depends on the storage system's internal cleanup schedule; the 24-hour SLA for deletion is a best-effort guarantee, not a real-time deletion.
