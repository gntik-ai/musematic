# Feature Specification: Generic S3 Storage — Remove MinIO Hard Dependency

**Feature Branch**: `057-generic-s3-storage`
**Created**: 2026-04-18
**Status**: Draft
**Input**: Brownfield infrastructure refactor — convert platform object-storage configuration and deployment from MinIO-specific to generic S3-compatible (Hetzner, AWS, Cloudflare R2, Wasabi, DigitalOcean Spaces, Backblaze B2, etc.); MinIO remains a supported deployment option for dev/self-hosted installs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Operator installs platform with managed external S3 provider (Priority: P1)

A platform operator wants to deploy the platform on Kubernetes using a managed object-storage provider (e.g., Hetzner Object Storage, AWS S3, Cloudflare R2) rather than self-hosting object storage. They expect to supply credentials and an endpoint URL and have the platform create and use the required buckets without ever deploying an internal MinIO workload.

**Why this priority**: Highest-value outcome — removes infrastructure complexity, eliminates operational burden of running a distributed object store, reduces cloud resource cost, and unblocks deployments in environments where MinIO is not permitted (regulated clouds, minimal-footprint installs).

**Independent Test**: Install the platform on a fresh cluster using a managed S3 provider (e.g., Hetzner Object Storage) credentials. Verify no MinIO pods are deployed, required buckets exist on the external provider, and artifacts (agent packages, execution artifacts, reasoning traces) are written and read correctly through normal platform operations.

**Acceptance Scenarios**:

1. **Given** a fresh Kubernetes cluster and valid external S3 credentials, **When** the operator installs the platform and selects "external S3" as object-storage provider, **Then** no MinIO workload is deployed and all required buckets are created on the external provider within 2 minutes.
2. **Given** the platform is configured against an external S3 provider, **When** an agent publishes a package or an execution produces an artifact, **Then** the object is written to the configured provider and retrievable via normal read paths.
3. **Given** a platform configured against external S3 that uses virtual-hosted addressing (e.g., AWS S3), **When** the system resolves bucket URLs, **Then** all clients use virtual-hosted style correctly (no 400 errors caused by path-style requests).
4. **Given** a platform configured against external S3 that requires path-style addressing (e.g., Hetzner, MinIO), **When** the system resolves bucket URLs, **Then** all clients use path-style addressing correctly.

---

### User Story 2 — Existing installation continues operating on self-hosted MinIO (Priority: P1)

An existing installation uses self-hosted MinIO for object storage and cannot migrate to an external provider today. They expect to upgrade to the new platform version without changing any data or re-uploading objects, and to continue operating MinIO as a first-class, supported deployment option.

**Why this priority**: Backward compatibility is non-negotiable — any data loss or forced migration would block adoption. The MinIO path must remain fully functional and operationally identical to today.

**Independent Test**: Take a pre-upgrade installation running self-hosted MinIO with populated buckets, upgrade to the new version, and verify every bucket still exists with all objects intact, every read/write path works unchanged, and the MinIO Helm chart still deploys when selected.

**Acceptance Scenarios**:

1. **Given** an existing installation running self-hosted MinIO with populated buckets, **When** the upgrade to the new platform version completes, **Then** all pre-existing objects remain readable and writable without any data migration step.
2. **Given** an operator installing a new cluster and choosing "self-hosted MinIO" at install time, **When** the install completes, **Then** a MinIO workload is deployed on the cluster and configured as the object-storage backend.
3. **Given** an existing installation on self-hosted MinIO, **When** the operator opts to migrate to an external provider later, **Then** they can do so by re-configuring credentials and running the bucket-init process, with object-copy handled out-of-band.

---

### User Story 3 — Developer runs the platform locally against containerized MinIO (Priority: P2)

A developer working on the platform runs local services via the standard dev-stack. They need a lightweight, ephemeral object store on their workstation that requires no external account and no credentials beyond local defaults.

**Why this priority**: Developer productivity and test reproducibility — a self-contained local stack is essential for new-contributor onboarding and for CI environments that cannot reach external providers. This is secondary to production install paths.

**Independent Test**: Start the local dev stack on a clean workstation, run the platform test suite, and verify all object-storage-dependent tests pass against the local containerized MinIO with zero external network calls.

**Acceptance Scenarios**:

1. **Given** a fresh clone of the repository on a developer workstation, **When** they start the local dev stack, **Then** a local MinIO container is available and the platform is configured to use it with default credentials.
2. **Given** the local dev stack is running, **When** the developer runs the full test suite, **Then** all object-storage-dependent tests pass without requiring any external S3 provider credentials.

---

### User Story 4 — Operator observes S3 backend health regardless of provider (Priority: P2)

An operator watches the platform's health endpoints and expects to see clear status for the object-storage backend — which provider is in use, which endpoint, and whether it is reachable — without that information leaking secrets.

**Why this priority**: Operational observability — diagnosing incidents requires knowing which backend is configured and whether the platform can reach it. Not blocking for initial deploy but essential before production cutover.

**Independent Test**: Query the platform health endpoint under three configurations (external S3 reachable, external S3 unreachable, self-hosted MinIO) and verify the reported provider name, endpoint indicator, and health status are accurate and never contain credentials.

**Acceptance Scenarios**:

1. **Given** the platform is configured against a reachable S3 backend, **When** an operator queries the health endpoint, **Then** the response reports object-storage status as healthy, names the provider, and indicates the endpoint (or "default" for AWS) without exposing credentials.
2. **Given** the configured S3 endpoint is temporarily unreachable, **When** an operator queries the health endpoint, **Then** the response reports object-storage status as unhealthy and includes a non-sensitive error indicator.
3. **Given** any S3 provider, **When** the health endpoint response is logged or exposed to third-party monitoring, **Then** no credential (access key, secret key, or session token) ever appears in the response body or headers.

---

### Edge Cases

- **Empty endpoint URL**: When the endpoint URL is empty, the system MUST treat that as "use provider default" (AWS S3 default regional endpoint), not error out.
- **Path-style vs virtual-hosted mismatch**: If addressing style is misconfigured for the provider (e.g., virtual-hosted against a provider that only supports path-style), the system MUST surface a clear, provider-aware error on first bucket access — not a generic "400 Bad Request".
- **Partial bucket creation**: If the bucket-initialization process fails midway (e.g., credential valid for some buckets but provider quota exceeded), the system MUST report which buckets succeeded and which failed, and be safely re-runnable (idempotent).
- **Upgrade with changed addressing style**: An existing MinIO installation upgrading to the new version MUST have its configuration auto-derived to use path-style (MinIO's only supported style), without operator intervention.
- **Credential rotation**: When S3 credentials are rotated in the cluster secret, running workloads MUST pick up new credentials on their next client refresh without requiring a full platform restart.
- **Bucket name collisions**: If the configured bucket prefix produces a bucket name that already exists in the target S3 account (from a prior install or unrelated workload), the bucket-init process MUST detect this and proceed only when the bucket is owned by the install's credentials; otherwise it MUST abort with a clear error, never silently reuse a foreign bucket.
- **Dev-to-prod parity**: A developer who builds a feature against local MinIO MUST have their code run unchanged against external S3 in production — no provider-specific code paths inside the application.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The platform MUST expose a single set of object-storage configuration keys (endpoint URL, access key, secret key, region, bucket name prefix, addressing style, provider label) that are used uniformly by all control-plane components and satellite services.
- **FR-002**: The platform MUST accept an empty endpoint URL as "use provider default" (AWS S3 default) without requiring any other code changes.
- **FR-003**: The platform MUST support both path-style and virtual-hosted addressing styles, selectable via configuration, so that both AWS S3 (virtual-hosted) and self-hosted / Hetzner / MinIO (path-style) work without code changes.
- **FR-004**: The platform install process MUST allow the operator to choose between "self-hosted MinIO" and "external S3" at install time; the default for new installs MUST be "external S3".
- **FR-005**: When "external S3" is selected, the platform MUST NOT deploy any MinIO workload to the cluster.
- **FR-006**: When "self-hosted MinIO" is selected, the platform MUST deploy a MinIO workload using the existing bundled deployment assets and configure all services against it.
- **FR-007**: Existing installations running self-hosted MinIO MUST continue to operate identically after upgrading to the new platform version, with zero data migration, zero object re-upload, and zero forced downtime beyond a normal rolling restart.
- **FR-008**: The platform MUST provide a bucket-initialization process that creates every required bucket on the configured provider on install and upgrade, is idempotent (safe to re-run), and reports per-bucket success or failure.
- **FR-009**: The bucket-initialization process MUST NOT silently use a bucket it did not create if that bucket already exists under different ownership; it MUST either verify ownership via a write test or abort with a clear error.
- **FR-010**: The platform MUST surface the object-storage backend status (healthy/unhealthy, provider name, endpoint indicator) on the health endpoint without exposing credentials in any response body, header, or log entry.
- **FR-011**: Application code (business logic and service layers) MUST NOT contain references to a specific object-storage vendor; only configuration, client-initialization, and deployment artifacts are allowed to name a specific vendor.
- **FR-012**: The platform MUST provide a local developer stack that runs an ephemeral MinIO container with default credentials and requires no external provider account.
- **FR-013**: Credentials for the object-storage backend MUST be sourced from a secure configuration mechanism (e.g., Kubernetes Secret) and never stored in plaintext in deployment manifests, environment files committed to version control, or health-endpoint responses.
- **FR-014**: The platform MUST produce clear, provider-aware error messages when configuration is incompatible with the target provider (e.g., wrong addressing style) rather than generic HTTP 400 responses.
- **FR-015**: All existing automated tests that exercise object-storage behavior MUST continue to pass against the local MinIO dev stack without modification, proving test-suite provider-neutrality.
- **FR-016**: The platform MUST allow the operator to specify a bucket-name prefix so that multiple installs can share a single S3 account without bucket name collisions.
- **FR-017**: The operator install experience MUST capture all required S3 configuration (endpoint URL, region, access key, secret key, addressing style) when "external S3" is selected, and store those values as cluster secrets that all services reference.
- **FR-018**: All Go satellite services that read or write objects MUST honor the same object-storage configuration keys as the Python control plane, so that a single credential rotation covers both.
- **FR-019**: The platform's addressing-style setting MUST default to path-style for new installs (compatible with the widest set of providers including MinIO, Hetzner, Wasabi), with AWS-specific deployments opting into virtual-hosted style explicitly.
- **FR-020**: A non-MinIO install MUST produce a platform cluster whose workloads contain no MinIO-vendor strings in application code, logs, metrics, or health payloads except where the operator has explicitly selected MinIO as the provider.

### Key Entities

- **Object Storage Configuration**: The set of settings that together identify the backend — endpoint URL, access key, secret key, region, bucket name prefix, addressing style, provider label. Treated as a single logical unit for credential rotation and health reporting.
- **Bucket Set**: The collection of logical buckets the platform requires (e.g., agent packages, execution artifacts, reasoning traces, sandbox outputs, evidence bundles, simulation artifacts, backups). Each bucket is identified by a logical name; the real bucket name is `{prefix}-{logical_name}`.
- **Provider Label**: A human-readable identifier for the backend in use (e.g., `minio`, `aws`, `hetzner`, `r2`, `wasabi`, `generic`). Informational only — does not change application behavior, only health-endpoint display.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A platform install against a managed external S3 provider completes and reaches "ready" state without deploying any MinIO workload to the target cluster.
- **SC-002**: An existing installation running self-hosted MinIO can be upgraded to the new version and 100% of pre-upgrade objects remain readable and writable with zero data migration steps.
- **SC-003**: The bucket-initialization process creates all required buckets on the configured provider within 2 minutes of install/upgrade start.
- **SC-004**: Application source code contains zero vendor-specific object-storage references outside of the configuration surface, client-initialization code, and deployment assets; a full-tree search confirms this invariant.
- **SC-005**: The health endpoint reports object-storage backend status (healthy/unhealthy + provider + endpoint indicator) in 100% of configurations without any credential value appearing in the response or in observability pipelines.
- **SC-006**: The full object-storage-related test suite passes against the local MinIO dev stack and against at least two external S3 providers (e.g., AWS S3 and one S3-compatible third-party) with identical test code.
- **SC-007**: An operator can complete initial install configuration of an external S3 backend (credential + endpoint entry) in under 5 minutes.
- **SC-008**: A credential rotation on the configured S3 backend propagates to all running workloads within the standard cluster-secret refresh interval (under 60 seconds) without requiring a full platform restart.

## Assumptions

- The platform's existing storage operations (bucket reads/writes, lifecycle rules, multipart uploads) already conform to the generic S3 protocol and require no protocol-level changes — only configuration and client-initialization changes.
- Operators using external S3 providers are responsible for provider-side concerns (quota, lifecycle, billing, regional failover); the platform does not replicate those capabilities.
- The platform assumes any S3-compatible provider it is pointed at supports the subset of the S3 API the platform already exercises (basic object CRUD, multipart upload, listing, head). Providers with gaps are out of scope.
- Data migration between backends (e.g., from self-hosted MinIO to external S3) is an operator-driven, out-of-band exercise using standard S3 copy tools; the platform does not provide an automated migration.
- Credential-rotation cadence and policy are operator-controlled; the platform only guarantees that rotated credentials are picked up within the cluster secret refresh interval.
- The "informational provider label" is not used for business logic — only for health-endpoint display; mislabeling does not cause functional differences.

## Dependencies

- The platform's existing object-storage client wrapper is already backed by generic S3 SDKs in both Python (boto3/aioboto3) and Go (aws-sdk-go-v2); this feature is primarily a configuration and deployment refactor, not a protocol rewrite.
- Constitutional guidance **AD-16** ("Generic S3 storage, MinIO optional") and **Critical Reminder 29** ("No MinIO in application code") define the architectural target this feature delivers.
- The existing Helm chart layout and installer scripts are modified; the change is additive (new provider-selection flow) plus a safety switch (MinIO deployment gated behind an explicit provider choice).
- Existing backup/restore operations (feature 048) that reference the object-storage backend MUST continue to function under both provider modes; no changes expected beyond configuration.

## Out of Scope

- Automated data migration between MinIO and external S3 providers.
- Multi-provider active-active replication (e.g., dual-write to MinIO and AWS S3).
- Changes to bucket layout, object key schemes, or lifecycle policies.
- Changes to how the platform authorizes object access (IAM, signed URLs, presigned uploads) — behavior remains identical.
- Vault integration for credential management — K8s Secrets remain the credential store; Vault is a possible future layer.
- Provider-specific tuning (e.g., AWS S3 Intelligent-Tiering, R2 cache rules); operators configure these on the provider side.
