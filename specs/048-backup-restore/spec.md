# Feature Specification: Backup and Restore

**Feature Branch**: `048-backup-restore`  
**Created**: 2026-04-17  
**Status**: Draft  
**Input**: User description for unified backup orchestration across all 8 data stores with verification, restore, and operator CLI integration.  
**Requirements Traceability**: TR-092 (Durable recovery), FR-132 (Backup and restore)

## User Scenarios & Testing

### User Story 1 - Create a Full Platform Backup (Priority: P1)

An operator runs a backup command to capture the complete state of all 8 data stores before a major upgrade. The system backs up each store in dependency order — starting with the relational database (the system of record) and proceeding through vector, graph, analytics, cache, search, and object stores. Each artifact is checksummed for integrity. After all stores are backed up, the system uploads every artifact to a designated storage location and records a manifest containing the backup tag, store-level metadata (artifact size, checksum, duration), and the overall completion status. The operator sees a progress summary showing each store's backup status (completed, failed, skipped) and the total elapsed time.

**Why this priority**: Backup is the foundation of disaster recovery. Without reliable full-platform backups, the organization cannot recover from data loss, corruption, or failed upgrades. Every other backup capability (restore, listing, partial restore) is useless without the ability to create a backup first.

**Independent Test**: Run the backup command against a platform with data in all 8 stores. Verify a manifest is created with entries for all stores. Verify checksums match the uploaded artifacts. Verify the backup tag follows the naming convention.

**Acceptance Scenarios**:

1. **Given** all 8 data stores are running and accessible, **When** the operator runs the backup command, **Then** the system backs up all stores in dependency order and reports success for each store.
2. **Given** a backup is in progress, **When** each store's backup completes, **Then** the system computes a SHA-256 checksum for the artifact before uploading it to storage.
3. **Given** all store backups and uploads complete, **When** the backup finishes, **Then** a manifest file is created containing: backup tag, creation timestamp, per-store entries (artifact name, size in bytes, SHA-256 checksum, duration in seconds, status), and overall status.
4. **Given** the operator does not specify a tag, **When** the backup runs, **Then** the system generates a tag in the format `backup-{YYYYMMDD-HHMMSS}-{sequence}`.
5. **Given** the operator specifies a custom tag, **When** the backup runs, **Then** the system uses the custom tag and validates it contains only alphanumeric characters, hyphens, and underscores.
6. **Given** the backup is running, **When** the operator views the terminal, **Then** they see real-time progress showing: current store being backed up, elapsed time per store, and a running total.

---

### User Story 2 - Restore from a Full Backup (Priority: P1)

An operator restores the platform from a previously created backup after a catastrophic failure. They specify the backup identifier, and the system retrieves the manifest, verifies all artifact checksums before starting any restore, and then restores each store in reverse dependency order. The operator sees progress as each store is restored. After completion, the system reports any discrepancies and confirms data integrity.

**Why this priority**: Restore is the other half of disaster recovery — backups are useless without a reliable restore process. Operators must be confident that a restore will faithfully reproduce the exact platform state that was backed up, and that corrupted artifacts are detected before any destructive action is taken.

**Independent Test**: Create a backup. Delete data from at least one store. Run the restore command with the backup identifier. Verify the deleted data is restored. Verify checksums were verified before restore began.

**Acceptance Scenarios**:

1. **Given** a valid backup identifier, **When** the operator runs the restore command, **Then** the system downloads the manifest, lists all stores to be restored, and prompts for confirmation before proceeding.
2. **Given** the operator confirms the restore, **When** the system begins, **Then** it downloads each artifact and verifies its SHA-256 checksum against the manifest before restoring any store.
3. **Given** all checksums pass, **When** the restore proceeds, **Then** stores are restored in reverse dependency order (object storage first, relational database last) to maintain referential consistency.
4. **Given** a checksum fails for any artifact, **When** the verification step detects the mismatch, **Then** the restore is aborted entirely and no stores are modified.
5. **Given** the restore is in progress, **When** each store completes, **Then** the system reports the store name, status (restored/failed), and duration.
6. **Given** all stores are restored, **When** the restore finishes, **Then** the system reports overall success, total duration, and the number of stores restored.

---

### User Story 3 - List Available Backups (Priority: P1)

An operator needs to find a specific backup to restore from. They run the backup list command and see a table of all available backups sorted by creation date (most recent first). Each entry shows the backup tag, creation timestamp, total size, number of stores included, and status. In headless mode, the same information is returned as structured data for integration with automation scripts.

**Why this priority**: Operators cannot restore from a backup if they don't know what backups are available. The list command is a prerequisite for any restore workflow and is trivial to implement once the manifest format is defined.

**Independent Test**: Create two backups with different tags. Run the list command. Verify both appear in the listing with correct metadata. Run with the headless flag and verify structured output.

**Acceptance Scenarios**:

1. **Given** multiple backups exist in storage, **When** the operator runs the list command, **Then** all backups are displayed in a table sorted by creation date (newest first) with columns: tag, created, total size, stores, status.
2. **Given** the operator runs the list command with the headless output flag, **When** the command completes, **Then** the output is structured data (one entry per backup) containing: tag, timestamp, size, store count, status.
3. **Given** no backups exist, **When** the operator runs the list command, **Then** the system displays a message indicating no backups are available and exits cleanly.

---

### User Story 4 - Restore a Single Store (Priority: P2)

An operator discovers that one data store has become corrupted while the rest of the platform is healthy. Instead of performing a full restore (which would require downtime for all services), they restore only the affected store from a backup. The system extracts the single store's artifact from the specified backup, verifies its checksum, and restores only that store, leaving all other stores untouched.

**Why this priority**: Partial restore minimizes downtime. In most failure scenarios, only one store is affected — restoring the entire platform unnecessarily disrupts all services. This depends on the full restore capability (US2) being in place first, as partial restore uses the same underlying per-store restore logic.

**Independent Test**: Create a backup. Corrupt data in one store only. Run the restore command with the store filter. Verify only that store is restored. Verify all other stores are untouched.

**Acceptance Scenarios**:

1. **Given** a valid backup identifier and a specific store name, **When** the operator runs the restore command with the store filter, **Then** only the specified store is restored from the backup.
2. **Given** the operator requests a partial restore, **When** the checksum verification runs, **Then** only the artifact for the specified store is verified (not all artifacts in the backup).
3. **Given** the operator specifies a store name that does not exist in the backup manifest, **When** the command runs, **Then** it reports an error listing the available stores in that backup and exits without modifying anything.
4. **Given** a partial restore completes, **When** the operator checks the restored store, **Then** the data matches the backup. All other stores retain their current (pre-restore) state.

---

### User Story 5 - Verify Backup Integrity (Priority: P2)

An operator wants to confirm that a backup is restorable before an emergency occurs. They run a verification command against a backup identifier. The system downloads each artifact and verifies its checksum against the manifest without restoring any data. The operator sees a pass/fail result for each store's artifact.

**Why this priority**: Proactive verification catches silent corruption in backup storage before an emergency. Without verification, operators only discover corrupted backups during a crisis — the worst possible time. This depends on the backup creation (US1) being functional.

**Independent Test**: Create a backup. Run the verify command. Verify all stores pass. Manually corrupt one artifact in storage. Run verify again. Verify the corrupted store fails while others pass.

**Acceptance Scenarios**:

1. **Given** a valid backup identifier, **When** the operator runs the verify command, **Then** the system downloads each artifact and compares its SHA-256 checksum against the manifest.
2. **Given** all checksums match, **When** verification completes, **Then** the system reports all stores as verified with a total "pass" status.
3. **Given** one or more artifacts have mismatched checksums, **When** verification completes, **Then** the system reports which specific stores failed verification and exits with a non-zero status code.
4. **Given** an artifact is missing from storage (deleted or unavailable), **When** the verification runs, **Then** the system reports the missing artifact as a failure with a clear error message.

---

### User Story 6 - Automated Scheduled Backups (Priority: P3)

An operator configures the platform to create backups automatically on a recurring schedule. The system creates backups at the specified interval, applies a retention policy (deleting backups older than the configured retention period), and reports any failures through the platform's alerting system. The operator does not need to be present for backups to occur.

**Why this priority**: Manual backups are error-prone and require operator attention. Automated backups ensure consistent data protection without human intervention. This depends on all backup capabilities (US1–US5) being reliable first.

**Independent Test**: Configure a schedule with a short interval (e.g., every 5 minutes for testing). Wait for two backup cycles. Verify two backups were created. Configure a retention period shorter than the oldest backup. Verify the oldest backup is deleted automatically.

**Acceptance Scenarios**:

1. **Given** a backup schedule is configured, **When** the scheduled time arrives, **Then** a full backup is created automatically using the same process as the manual backup command.
2. **Given** a retention policy is configured (e.g., keep backups for 30 days), **When** a new backup completes, **Then** the system deletes backups older than the retention period.
3. **Given** a scheduled backup fails, **When** the failure occurs, **Then** the system records the failure with the error message and continues to attempt future scheduled backups.
4. **Given** a scheduled backup is running, **When** the operator manually triggers a backup, **Then** the manual backup queues and runs after the scheduled backup completes (no concurrent backups).

---

### Edge Cases

- What happens when a store is unreachable during backup? The backup records that store as "failed" in the manifest. The operator is warned but other stores continue backing up. The overall backup status is "partial."
- What happens when backup storage is full? The upload step fails with a clear error. Artifacts already uploaded are not rolled back — the operator can retry after freeing space or changing the storage target.
- What happens when a restore is interrupted mid-way (e.g., network failure)? The restore records which stores were completed and which were pending. The operator can re-run the restore — already-restored stores are overwritten (restore is idempotent per store).
- What happens when two operators trigger backups simultaneously? Only one backup can run at a time. The second operator receives a message that a backup is already in progress and must wait.
- What happens when a backup's artifact format is from an older version? The restore command checks the manifest's schema version. If the version is incompatible, it reports an error and suggests using the matching CLI version.
- What happens when restoring a store that has active connections? The restore operation reports a warning about active connections. For stores that support it, connections are drained gracefully before restore. For others, the operator must stop dependent services first.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST back up all 8 data stores (relational database, vector search, graph database, analytics engine, cache, full-text search, event streaming offsets, object storage metadata) in a single orchestrated operation
- **FR-002**: Backups MUST be created in dependency order to ensure consistency — the relational database (system of record) is backed up first, followed by dependent stores
- **FR-003**: Each backup artifact MUST have a SHA-256 checksum computed at creation time and stored in the backup manifest
- **FR-004**: The backup manifest MUST contain: backup tag, creation timestamp, schema version, per-store entries (artifact name, size, checksum, duration, status), and overall status
- **FR-005**: The system MUST assign a backup tag in the format `backup-{YYYYMMDD-HHMMSS}-{NNN}` when no custom tag is provided
- **FR-006**: Backup artifacts MUST be uploaded to a configurable storage location (default: a designated bucket in the platform's object storage)
- **FR-007**: The system MUST prevent concurrent backup operations using a distributed lock
- **FR-008**: The restore command MUST verify all artifact checksums against the manifest before modifying any data store
- **FR-009**: If any checksum verification fails, the restore MUST abort entirely without modifying any store
- **FR-010**: Restore MUST proceed in reverse dependency order (object storage first, relational database last)
- **FR-011**: The restore command MUST prompt for operator confirmation before proceeding, showing the list of stores to be restored
- **FR-012**: The system MUST support restoring a single named store from a backup without affecting other stores
- **FR-013**: The list command MUST display all available backups sorted by creation date (newest first) with tag, timestamp, size, store count, and status
- **FR-014**: The list command MUST support structured output for headless/scripted use
- **FR-015**: A verify command MUST check all artifact checksums in a backup without restoring any data
- **FR-016**: If any store backup fails during a full backup, the system MUST continue backing up remaining stores and mark the overall status as "partial"
- **FR-017**: The system MUST support automated scheduled backups at a configurable interval with retention-based cleanup
- **FR-018**: Each backup and restore operation MUST log estimated and actual duration for operational planning

### Key Entities

- **Backup Manifest**: The metadata record for a backup operation. Contains the backup tag (unique identifier), creation timestamp, schema version, a list of store entries, and overall status (complete/partial/failed). Stored alongside backup artifacts in the configured storage location.
- **Store Entry**: A single store's record within a backup manifest. Contains the store name, artifact file name, artifact size in bytes, SHA-256 checksum, backup duration in seconds, and status (completed/failed/skipped).
- **Backup Artifact**: A binary file containing a store's backed-up data. Identified by a file name derived from the backup tag and store name. Format is store-specific (e.g., SQL dump, RDB snapshot, collection snapshot archive).
- **Backup Schedule**: A recurring backup configuration. Contains the schedule expression (interval), retention period, the storage target, and the last execution result.
- **Restore Plan**: The ordered list of stores to restore from a backup. Contains the backup tag, the list of stores (filtered or full), the dependency-ordered execution sequence, and the verification status.

## Success Criteria

### Measurable Outcomes

- **SC-001**: An operator can create a full platform backup of all 8 stores in under 30 minutes on a platform with up to 50 GB of total data
- **SC-002**: An operator can restore the full platform from a backup in under 45 minutes on the same data volume
- **SC-003**: 100% of backup artifacts have verified checksums — no silent data corruption goes undetected
- **SC-004**: A partial (single-store) restore completes without any downtime to unaffected stores
- **SC-005**: The operator can find and select any past backup within 10 seconds using the list command
- **SC-006**: Automated scheduled backups run without operator intervention for at least 90 consecutive days with zero missed backups (excluding infrastructure outages)
- **SC-007**: A corrupted backup artifact is detected by the verify or restore command 100% of the time before any data modification occurs

## Assumptions

- The `platform-cli` (feature 045) is the host for all backup and restore commands — this feature implements the backup orchestration logic within that CLI
- Each data store's native backup tool is available on the system where the CLI runs (e.g., the database dump utility is installed or accessible via the store's API)
- The default backup storage location is a bucket in the platform's object storage (MinIO) — the same object storage that is itself being backed up (its metadata, not the backup bucket)
- Backup and restore operations are expected to run during maintenance windows — the system does not guarantee zero-downtime backups for all stores (some stores require quiescing writes)
- The event streaming system (Kafka) backup covers consumer group offsets only — topic data is ephemeral and not backed up
- The schema version in the manifest enables forward compatibility — older CLIs can read older manifests, but newer manifest formats may require a CLI upgrade
- Concurrent backup prevention uses the same distributed lock mechanism as the installer (feature 045) — ConfigMap lease in Kubernetes, file lock in local mode
- The `platform-cli backup create --stores` flag for backing up specific stores is not in scope — full backup only for creation; partial restore is supported via `--stores` on restore
