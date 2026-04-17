# Feature Specification: Installer and Operations CLI

**Feature Branch**: `045-installer-operations-cli`  
**Created**: 2026-04-16  
**Status**: Draft  
**Input**: User description for building the platform CLI tool for installation, diagnostics, administration, backup/restore, and headless automation across all deployment modes.  
**Requirements Traceability**: TR-095–098, TR-111, TR-153–155; FR-001–006, FR-143–146

## User Scenarios & Testing

### User Story 1 - Install Platform on Kubernetes (Priority: P1)

A platform operator prepares a fresh Kubernetes cluster and runs the installer CLI to deploy the complete platform. The CLI first runs a series of preflight checks — verifying cluster access, namespace permissions, storage class availability, and ingress controller presence. If any check fails, the CLI reports the failure with remediation instructions and exits without making changes. Once preflight succeeds, the CLI generates all required secrets (database passwords, cache credentials, API signing keys) and stores them securely. It then installs each platform component in the correct dependency order — data stores first, then satellite services, and finally the control plane. After all components are deployed, the CLI waits for every deployment to report ready, runs schema migrations across all data stores, creates an initial administrator account, and displays the one-time admin credentials on screen. The entire process completes within 15 minutes on a standard cluster. If the operator runs the installer again on an already-deployed cluster, it detects the existing installation and either skips or upgrades components as appropriate — the installation is idempotent.

**Why this priority**: Kubernetes is the production deployment target. Without a reliable, automated installer, every deployment is a manual, error-prone multi-hour process involving dozens of individual Helm commands, secret generation, migration scripts, and health checks.

**Independent Test**: Run the installer against a fresh Kubernetes cluster. Verify all preflight checks pass. Verify all platform services reach "ready" state. Verify schema migrations complete. Log in with the displayed admin credentials. Run the installer a second time — verify it completes without errors and does not duplicate resources.

**Acceptance Scenarios**:

1. **Given** a fresh Kubernetes cluster with kubectl access, **When** the operator runs the install command targeting Kubernetes, **Then** preflight checks verify cluster access, namespace permissions, storage class, and ingress controller, reporting pass/fail for each.
2. **Given** preflight passes, **When** the installer proceeds, **Then** it generates unique secrets for each service (admin password, database passwords, cache password, graph database password, analytics password, search password, API signing key) and stores them in the cluster's secret management.
3. **Given** secrets are generated, **When** the installer deploys components, **Then** it installs them in dependency order: relational database, cache, event backbone, vector search, graph database, analytics store, full-text search, object storage, runtime controller, reasoning engine, sandbox manager, and control plane.
4. **Given** all deployments are running, **When** the installer runs post-deployment steps, **Then** it executes schema migrations for all data stores, creates an initial admin user, and displays the admin credentials on screen exactly once.
5. **Given** a fully deployed platform, **When** the operator runs the install command again, **Then** the installer detects the existing deployment and completes without errors, duplicating no resources and preserving existing data.
6. **Given** any preflight check fails (e.g., no storage class), **When** the installer runs, **Then** it reports the specific failure with remediation instructions and exits without making any changes.

---

### User Story 2 - Install Platform Locally for Development (Priority: P1)

A developer runs the installer CLI to start the entire platform on their local machine for development and testing. The CLI uses lightweight alternatives for infrastructure components — an embedded relational database instead of a full database cluster, in-memory vector search, an embedded cache (or mock), filesystem-based object storage, and an in-process event queue. Components that are not essential for development (graph database, analytics store, full-text search) are replaced with lightweight fallbacks. The reasoning engine runs as a local subprocess. The entire platform starts within a single process with all service profiles active. The local installation completes in under 30 seconds.

**Why this priority**: Local development is the most frequent use case — every developer needs to run the platform daily. A fast, zero-infrastructure local mode is essential for developer productivity and onboarding.

**Independent Test**: Run the local install command on a developer machine without any infrastructure installed. Verify the platform starts within 30 seconds. Verify the developer can access the platform UI. Verify basic workflows execute correctly against the lightweight backends.

**Acceptance Scenarios**:

1. **Given** a developer machine with no infrastructure installed, **When** the developer runs the install command targeting local mode, **Then** the platform starts within 30 seconds using embedded/lightweight alternatives for all infrastructure components.
2. **Given** local mode is running, **When** the developer accesses the platform UI, **Then** it is fully functional for development workflows — creating workspaces, triggering executions, viewing conversations.
3. **Given** local mode, **When** the developer triggers a workflow execution, **Then** it executes against the local reasoning engine subprocess and returns results, demonstrating end-to-end functionality without external dependencies.
4. **Given** local mode is already running, **When** the developer restarts the install command, **Then** it either resumes or restarts cleanly without data corruption in the embedded database.

---

### User Story 3 - Diagnose Platform Health (Priority: P1)

A platform operator runs the diagnose command to check the health and connectivity of every platform component. The CLI checks each of the 8 data stores, 5 satellite services, and configured model providers. For each check, the CLI reports a green (healthy), yellow (degraded), or red (unreachable/failed) status. Checks include basic connectivity, authentication, and a lightweight operation (e.g., ping, simple query). The operator can request machine-readable output for use in CI/CD pipelines and monitoring scripts. The entire diagnostic run completes within 30 seconds.

**Why this priority**: Diagnostics are essential for both initial post-installation verification and ongoing operational troubleshooting. Without a diagnostic tool, operators must manually check each service individually — a tedious, error-prone process.

**Independent Test**: Run the diagnose command against a running platform. Verify each service shows green/yellow/red status. Intentionally stop one service — re-run diagnose and verify it reports red for that service. Run with the machine-readable flag and verify the output is valid structured data parseable by scripts.

**Acceptance Scenarios**:

1. **Given** a running platform, **When** the operator runs the diagnose command, **Then** the CLI checks connectivity and health for all 8 data stores, 5 satellite services, and configured model providers, displaying green/yellow/red status for each.
2. **Given** one service is unreachable, **When** the diagnose command runs, **Then** that service shows red status with an error description, while all other services show their actual status.
3. **Given** the diagnose command, **When** the operator includes the machine-readable output flag, **Then** the output is valid structured data suitable for parsing by CI/CD scripts.
4. **Given** the diagnose command, **When** the operator includes the auto-remediation flag, **Then** the CLI attempts to fix known issues (e.g., restarting a failed deployment, clearing a stuck lock) and reports what was attempted and whether it succeeded.
5. **Given** any deployment mode (Kubernetes, local, or other), **When** the diagnose command runs, **Then** it completes all checks within 30 seconds.

---

### User Story 4 - Backup and Restore Platform Data (Priority: P2)

A platform operator creates a complete backup of all platform data stores. The CLI orchestrates the backup process across every data store — relational database, cache state, event backbone offsets, vector embeddings, graph data, analytics tables, full-text indices, and object storage. Each backup is tagged with a timestamp and sequence number. The backup artifacts are uploaded to a designated backup storage location with checksums for integrity verification. When the operator needs to restore, they specify a backup identifier and the CLI restores all data stores to that point in time, verifying checksums before applying.

**Why this priority**: Backup/restore is critical for disaster recovery and operational safety. However, it depends on having a working installation first (US1/US2) and a way to verify health afterward (US3), so it naturally follows the installation and diagnostic capabilities.

**Independent Test**: Run a backup on a platform with test data. Verify backup artifacts are created for each data store. Verify checksums are generated. Delete test data. Run restore from the backup. Verify all data is restored correctly.

**Acceptance Scenarios**:

1. **Given** a running platform with data, **When** the operator runs the backup create command, **Then** the CLI creates backup snapshots for each data store, tags them with a timestamp and sequence number, and uploads them to the backup storage location.
2. **Given** a completed backup, **When** the operator lists backups, **Then** they see all available backups with their timestamp, sequence number, size, and integrity status.
3. **Given** a valid backup identifier, **When** the operator runs the restore command, **Then** the CLI verifies checksums for all backup artifacts, restores each data store to the backed-up state, and reports the result for each store.
4. **Given** a backup with a corrupted artifact (checksum mismatch), **When** the operator runs restore, **Then** the CLI halts before restoring any data and reports which artifact failed verification.
5. **Given** a platform with active executions, **When** the operator runs a backup, **Then** the CLI warns that active executions may produce inconsistent snapshots and offers to proceed or wait.

---

### User Story 5 - Install on Docker Compose / Swarm / Incus (Priority: P2)

A platform operator deploys the platform on infrastructure other than Kubernetes — Docker Compose for small teams, Docker Swarm for production clusters without Kubernetes, or Incus for container-based deployments. The CLI adapts its deployment strategy to each target: generating Docker Compose files, Swarm stack definitions, or Incus profiles as appropriate. Preflight checks, secret generation, dependency ordering, migration execution, and admin user creation follow the same logical flow as the Kubernetes installer, adapted to the deployment target's capabilities and tooling.

**Why this priority**: While Kubernetes is the primary production target, supporting additional deployment modes broadens the platform's accessibility. This story is P2 because the core installation logic (US1) must be proven on Kubernetes first, then adapted to other targets.

**Independent Test**: Run the install command targeting Docker Compose. Verify all services start. Access the platform UI. Run diagnose — verify all green. Repeat for Swarm and Incus modes.

**Acceptance Scenarios**:

1. **Given** a machine with Docker Compose installed, **When** the operator runs the install command targeting Docker mode, **Then** the CLI generates a Compose file, starts all services in dependency order, runs migrations, and displays admin credentials.
2. **Given** a Docker Swarm cluster, **When** the operator runs the install command targeting Swarm mode, **Then** the CLI generates a stack definition, deploys services across the swarm, runs migrations, and displays admin credentials.
3. **Given** an Incus host, **When** the operator runs the install command targeting Incus mode, **Then** the CLI creates container profiles, launches containers, runs migrations, and displays admin credentials.
4. **Given** any non-Kubernetes deployment, **When** the operator runs diagnose, **Then** all service health checks pass and the platform is fully functional.

---

### User Story 6 - Upgrade Platform Version (Priority: P2)

A platform operator upgrades an existing platform deployment to a newer version. The CLI detects the currently installed version, downloads or references the target version artifacts, performs a rolling upgrade of each component in the correct order, runs any pending schema migrations, and verifies that all services are healthy after the upgrade. If any component fails to upgrade, the CLI stops the upgrade process and provides rollback instructions.

**Why this priority**: Upgrade is critical for long-running production deployments. However, it requires a stable installation path (US1) and diagnostic tooling (US3) as prerequisites, so it is prioritized after core installation.

**Independent Test**: Install a specific version. Run the upgrade command targeting a newer version. Verify all components are updated. Verify migrations ran. Run diagnose to verify all services are healthy.

**Acceptance Scenarios**:

1. **Given** a deployed platform at version N, **When** the operator runs the upgrade command targeting version N+1, **Then** the CLI detects the current version, validates the upgrade path, and begins a rolling upgrade.
2. **Given** an upgrade in progress, **When** each component is upgraded, **Then** it is upgraded in the correct dependency order and the CLI waits for each component to reach healthy status before proceeding to the next.
3. **Given** all components upgraded, **When** the CLI runs post-upgrade steps, **Then** it executes any pending schema migrations and verifies all services pass health checks.
4. **Given** a component fails during upgrade, **When** the failure is detected, **Then** the CLI stops the upgrade process, reports which component failed and why, and provides instructions for rolling back the failed component.

---

### User Story 7 - Headless / CI-CD Automation (Priority: P3)

A CI/CD pipeline uses the installer CLI in headless mode to automate platform provisioning for integration testing. The CLI accepts all configuration via command-line flags and environment variables — no interactive prompts. It exits with appropriate status codes (0 for success, non-zero for failure) and emits structured log output suitable for pipeline consumption. The pipeline can run install, diagnose, run tests, and tear down in a single scripted flow.

**Why this priority**: Headless automation is important for CI/CD but depends on the core CLI commands (US1, US3) being stable first. Most operators will use the CLI interactively initially; headless mode is an extension for mature deployments.

**Independent Test**: Run the install command with all configuration passed via environment variables and flags, with no terminal attached. Verify it completes without prompts. Verify exit code is 0. Verify structured log output contains all expected stages.

**Acceptance Scenarios**:

1. **Given** a CI/CD pipeline with no interactive terminal, **When** the install command runs with all configuration via flags and environment variables, **Then** it completes without any prompts and exits with code 0 on success.
2. **Given** headless mode, **When** a preflight check fails, **Then** the CLI exits with a non-zero status code and the structured log output includes the failure reason and remediation steps.
3. **Given** headless mode, **When** the diagnose command runs, **Then** it outputs machine-readable structured data to stdout and exits with code 0 if all checks pass, or non-zero if any check fails.
4. **Given** a completed headless install, **When** the pipeline proceeds to tear-down, **Then** the CLI can cleanly remove the installation (uninstall command or equivalent) without interactive confirmation.

---

### User Story 8 - Administer Platform (Priority: P3)

A platform administrator uses the CLI for routine administrative tasks — managing user accounts, viewing system status, adjusting platform settings, and managing service configurations. The CLI provides subcommands for common administrative operations that would otherwise require direct database access or API calls.

**Why this priority**: Administration commands are important for operational efficiency but are lower priority than installation, diagnostics, and backup — the foundational operational capabilities.

**Independent Test**: Run admin commands to list users, change a setting, view system status. Verify each command produces the expected output and the change is reflected in the platform.

**Acceptance Scenarios**:

1. **Given** a running platform, **When** the operator runs the admin user list command, **Then** it displays all platform users with their roles and status.
2. **Given** a running platform, **When** the operator runs the admin command to create a user, **Then** a new user account is created with the specified role and the operator can log in as that user.
3. **Given** a running platform, **When** the operator runs the admin command to view system status, **Then** it displays a summary of platform configuration, active deployments, and resource utilization.

---

### Edge Cases

- What happens when the network connection is lost mid-installation? The CLI saves a checkpoint of completed steps and allows resuming from the last checkpoint using a `--resume` flag.
- What happens when one data store migration fails but others succeed? The CLI reports exactly which migration failed, rolls back only that migration (if possible), and provides instructions for manual remediation. Other stores retain their successfully migrated state.
- What happens when the operator specifies a deployment mode that conflicts with the host environment (e.g., Kubernetes mode without kubectl)? The preflight check catches the incompatibility and reports it with a clear error before making any changes.
- What happens when backup storage is full during a backup? The CLI detects the write failure, cleans up any partial backup artifacts, and reports the storage issue with the amount of space needed.
- What happens when two operators run the installer simultaneously on the same cluster? The CLI acquires a distributed lock at the start; the second operator sees "Another installation is in progress" and is blocked until the first completes or times out.
- What happens when the operator has no internet access during Kubernetes install? The CLI supports an air-gapped mode where container images and charts are loaded from a local registry or archive.
- What happens when the standalone binary is run on an unsupported OS or architecture? The CLI exits immediately with a clear error listing supported platforms.

## Requirements

### Functional Requirements

- **FR-001**: CLI MUST support 5 deployment modes: Kubernetes, Docker Compose, Docker Swarm, Incus, and local
- **FR-002**: CLI MUST perform preflight checks before installation that verify environment prerequisites for the selected deployment mode and report pass/fail for each check with remediation instructions on failure
- **FR-003**: CLI MUST generate unique cryptographic secrets (database passwords, cache passwords, API signing keys) during installation and store them securely in the deployment target's secret management system
- **FR-004**: CLI MUST install platform components in a defined dependency order, waiting for each dependency to become healthy before proceeding to dependents
- **FR-005**: CLI MUST execute schema migrations for all data stores after deployment, including the relational database migration framework and initialization scripts for vector search, graph database, analytics store, and full-text search
- **FR-006**: CLI MUST create an initial administrator account and display the credentials exactly once during first installation
- **FR-007**: Installation MUST be idempotent — running the installer on an already-deployed platform MUST complete without errors, without duplicating resources, and without data loss
- **FR-008**: CLI MUST provide a local development mode that starts the entire platform in under 30 seconds using embedded/lightweight alternatives for all infrastructure components
- **FR-009**: Local mode MUST use an embedded relational database, in-memory vector search, embedded or mocked cache, filesystem-based object storage, and an in-process event queue
- **FR-010**: CLI MUST provide a diagnose command that checks connectivity and health for all 8 data stores, 5 satellite services, and configured model providers within 30 seconds
- **FR-011**: Diagnose command MUST report green (healthy), yellow (degraded), or red (unreachable) status for each checked component
- **FR-012**: Diagnose command MUST support a machine-readable output flag for CI/CD integration
- **FR-013**: Diagnose command MUST support an auto-remediation flag that attempts to fix known issues and reports results
- **FR-014**: CLI MUST provide a backup create command that orchestrates consistent backups across all data stores, tags each with a timestamp and sequence number, and uploads artifacts with checksums to a backup storage location
- **FR-015**: CLI MUST provide a backup restore command that verifies checksums before restoring and halts if any artifact fails verification
- **FR-016**: CLI MUST provide an upgrade command that detects the current version, performs rolling upgrades in dependency order, runs pending migrations, and verifies post-upgrade health
- **FR-017**: Upgrade command MUST halt on component failure and provide rollback instructions
- **FR-018**: CLI MUST support fully headless operation — all configuration via command-line flags and environment variables, no interactive prompts, appropriate exit codes, and structured log output
- **FR-019**: CLI MUST provide admin subcommands for common administrative operations: user management, system status, and platform settings
- **FR-020**: CLI MUST save installation checkpoints and support resuming from the last checkpoint on failure
- **FR-021**: CLI MUST acquire a distributed lock during installation to prevent concurrent installations on the same target
- **FR-022**: CLI MUST be distributable as both a package installable via a package manager and a standalone binary requiring no runtime dependencies
- **FR-023**: CLI MUST support air-gapped installation from a local registry or archive when no internet access is available

### Key Entities

- **DeploymentMode**: The target infrastructure type — Kubernetes, Docker, Swarm, Incus, or local. Determines which preflight checks, deployment strategies, and configuration templates are used.
- **PreflightCheck**: A single environment prerequisite verification — has a name, check type, pass/fail status, error message, and remediation instruction.
- **InstallationCheckpoint**: A record of completed installation steps — allows resuming a failed installation from the last successful step.
- **PlatformComponent**: A deployable unit (data store or service) — has a name, version, dependency list, health check endpoint, and deployment status.
- **Secret**: A generated credential — has a name, target component, value (encrypted at rest), and storage location.
- **BackupManifest**: A record of a complete backup run — has a timestamp, sequence number, list of per-store backup artifacts with checksums, total size, and status.
- **BackupArtifact**: A single data store's backup snapshot — has a store name, file path/URI, size, checksum, and format.
- **DiagnosticResult**: The outcome of a single health check — has a component name, status (green/yellow/red), latency, error description, and remediation suggestion.
- **UpgradePlan**: The sequence of component upgrades for a version transition — has source version, target version, ordered component list, migration scripts, and rollback instructions.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A fresh Kubernetes installation completes end-to-end (preflight through admin credential display) in under 15 minutes
- **SC-002**: All platform services pass health checks immediately after installation, with zero manual intervention required
- **SC-003**: The administrator can log in with the displayed credentials on the first attempt after installation
- **SC-004**: Running the installer a second time on an existing deployment completes without errors and preserves all existing data
- **SC-005**: Local development mode starts the complete platform in under 30 seconds on a standard developer machine
- **SC-006**: The diagnose command checks all platform components and reports results in under 30 seconds
- **SC-007**: Backup create produces verifiable, checksum-protected backup artifacts for all data stores
- **SC-008**: Restore from a valid backup returns all data stores to their backed-up state with zero data loss
- **SC-009**: The CLI operates fully headless — completing installation in a CI/CD pipeline with no interactive prompts, using only flags and environment variables
- **SC-010**: The standalone binary runs on supported platforms without any pre-installed runtime or dependencies
- **SC-011**: 95% of operators can complete their first Kubernetes installation without consulting documentation beyond the CLI's own help output and error messages

## Assumptions

- The operator has sufficient permissions on the target environment (cluster-admin for Kubernetes, docker group for Docker, sudo or equivalent for Incus)
- For Kubernetes mode, a running cluster with at least 3 worker nodes and 32GB total allocatable memory is available
- For Docker Compose mode, the host has Docker Engine 24+ and Docker Compose v2+ installed
- Container images are available from a registry (public or private) unless air-gapped mode is used
- The platform's existing schema migration framework (used by the control plane) is available and can be invoked programmatically by the CLI
- The backup storage location (a designated bucket or directory) is pre-configured and accessible by the operator
- The CLI inherits the authentication context of the user's environment (kubeconfig for Kubernetes, Docker socket for Docker)
- Incus support targets LXD/Incus 5.x container manager
- The `upgrade` command only supports upgrading forward (no downgrade path); rollback is handled by restoring from a pre-upgrade backup
- Docker Swarm, Incus, and air-gapped modes are not required for the initial release — they may be delivered incrementally after core Kubernetes and local modes
