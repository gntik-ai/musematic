# Feature Specification: Security Compliance and Supply Chain

**Feature Branch**: `074-security-compliance`
**Created**: 2026-04-23
**Status**: Draft
**Input**: User description: "New `security_compliance/` bounded context delivering SBOM generation, vulnerability scanning with release gating, penetration test tracking, zero-downtime automated secret rotation, Just-in-Time (JIT) credentials for privileged operations, cryptographic audit log chaining, and a compliance evidence substrate mapping to SOC2 / ISO27001 / HIPAA / PCI-DSS frameworks. Feature UPD-024 in the audit-pass constitution; implements FR-471 through FR-477."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Release engineer ships a release with SBOM + vulnerability gating (Priority: P1) 🎯 MVP

A release engineer tags a platform release. Before the image lands in the container registry, the CI pipeline produces a Software Bill of Materials for that release in both SPDX and CycloneDX formats, runs a battery of vulnerability scanners across every layer of the build (operating-system packages, Python dependencies, Node dependencies, Go modules, and application code), gates the release against severity thresholds, and attaches the signed SBOM + scan report to the release record. If a critical CVE is present in a runtime path, the release is blocked; if all scanners pass or findings are pre-accepted, the release proceeds and the evidence is persisted for later compliance review.

**Why this priority**: Supply-chain transparency is the first compliance question every enterprise buyer asks. Without SBOM + vulnerability gating, there is no honest story to tell about what ships in a release or whether it contains known vulnerabilities. MVP because every other capability in this feature (audit chain, rotation, JIT, compliance evidence) produces value on top of releases the organisation trusts to ship.

**Independent Test**: Trigger a platform release. Verify an SBOM (SPDX + CycloneDX) is generated, persisted, and attached to the GitHub release. Verify the scan report shows all configured scanners (container, Python, Go, JavaScript, SAST) ran and produced findings. Inject a stub high-severity CVE into a dependency; verify the release workflow fails at the vulnerability gate and no image is published. Remove the CVE; verify the release proceeds. No other user story needs to be implemented for this to deliver value.

**Acceptance Scenarios**:

1. **Given** a successful CI build is about to publish a release, **When** the pipeline runs, **Then** an SBOM is produced in both SPDX and CycloneDX formats, persisted to the platform, and attached as a release artefact.
2. **Given** a release is being gated, **When** every configured vulnerability scanner runs, **Then** each scanner's findings are normalised into a single structured report with a `max_severity` field and an overall `gating_result` of `passed` or `blocked`.
3. **Given** a scan reports a `critical`-severity vulnerability in a runtime dependency with no pre-accepted exception, **When** the gating rule evaluates, **Then** the release workflow fails with a clear message identifying the offending component, and no image is promoted.
4. **Given** a scan reports a `critical` vulnerability in a development-only dependency, **When** the gating rule evaluates, **Then** the release proceeds (per the constitution's tunable-threshold principle) but the finding is still persisted.
5. **Given** a release has successfully published, **When** an auditor queries the release's SBOM, **Then** the platform returns the stored SPDX + CycloneDX documents with a verifiable SHA-256 of each.

---

### User Story 2 — Compliance auditor verifies audit trail integrity (Priority: P1)

A compliance auditor is asked by an external assessor to prove that the platform's audit log has not been tampered with. The auditor opens the admin surface, requests an integrity check on the audit chain for a given time window, and the platform walks every entry, recomputes each link's cryptographic hash from its payload plus the previous entry's hash, and certifies that the chain is unbroken. The auditor exports a signed attestation covering the period, which they can submit to the assessor. Every audit event the platform writes anywhere enters this chain; breaking the chain would require simultaneous rewriting of every subsequent entry, which is detectable.

**Why this priority**: Tamper-evident audit logs are the second-most-common enterprise compliance question. P1 alongside US1 because it is the foundation underpinning every other compliance claim — SOC2, ISO27001, HIPAA, and PCI-DSS all require audit-log integrity. Required before the audit-pass features that depend on the audit chain (privacy operations, JIT issuance, secret rotations) can claim tamper-evidence.

**Independent Test**: Write 1,000 audit entries through the existing audit service. Run the integrity check; assert `valid` result. Manually corrupt a single entry in the database. Re-run integrity check; assert `invalid` result with the specific sequence number of the first broken link. Export a signed attestation for a time window; verify the attestation signature with a public key.

**Acceptance Scenarios**:

1. **Given** any existing audit-emitting bounded context writes an audit event, **When** the write completes, **Then** a corresponding chain entry is appended with a deterministic hash linking it to the previous entry.
2. **Given** the chain has N entries, **When** the integrity-check endpoint is invoked, **Then** every entry's hash is recomputed and compared; a single result of `valid` or `invalid` is returned along with the specific sequence number of the first invalid entry (if any).
3. **Given** an auditor requests an attestation for a time window, **When** the attestation is generated, **Then** the platform produces a signed document containing the start and end sequence numbers, the hashes of the boundary entries, and a cryptographic signature verifiable with the platform's public audit-signing key.
4. **Given** a database operator attempts to directly UPDATE an audit entry (bypassing the audit service), **When** the integrity check is next run, **Then** the chain is reported as broken at the tampered entry's sequence number.
5. **Given** the platform restarts, **When** it resumes writing audit entries, **Then** the chain continues seamlessly from the highest previous sequence number with the correct previous-hash reference.

---

### User Story 3 — Security officer rotates a production credential with zero downtime (Priority: P2)

A security officer configures a 90-day rotation schedule for a critical production credential (e.g. the database password). Before the scheduled rotation date the platform begins a dual-credential window: a new credential is provisioned, both old and new credentials are valid for a configurable overlap period, every downstream service that accepts the credential is informed and validates against either, and after the overlap window the old credential is revoked. The security officer receives notifications at each stage, sees the rotation reflected in the audit trail, and can trigger emergency rotation on demand. No requests fail during the rotation.

**Why this priority**: Automated secret rotation with zero downtime is a major operational risk reducer and a hard requirement for mature security posture. P2 because US1 and US2 are foundational to compliance claims, while rotation is an operational discipline built on top.

**Independent Test**: Configure a rotation schedule for a test credential with a 30-minute window. Trigger the rotation. Observe: new credential provisioned → overlap window begins → both credentials validated across a test load → overlap ends → old revoked. During the entire rotation, drive continuous authenticated requests; assert zero request failures. Verify the audit chain records each rotation stage.

**Acceptance Scenarios**:

1. **Given** a rotation schedule is configured for a secret, **When** the scheduled time approaches, **Then** the platform begins the rotation, emits a notification to configured recipients, and records an audit event at each stage of the rotation.
2. **Given** a rotation is in its dual-credential overlap window, **When** any service validates the credential, **Then** either the old or the new credential is accepted.
3. **Given** the overlap window has ended, **When** a service attempts to authenticate with the old credential, **Then** the request is rejected with an audit entry noting the post-overlap rejection.
4. **Given** a security incident requires immediate rotation, **When** the officer triggers emergency rotation, **Then** the rotation begins immediately and can optionally skip the overlap window (breaking-change acknowledged), with the emergency reason required in the audit trail.
5. **Given** continuous load during a rotation, **When** the rotation completes, **Then** the count of failed authentications attributable to the rotation is zero.

---

### User Story 4 — Engineer obtains a Just-in-Time credential for a privileged operation (Priority: P2)

An engineer needs to perform a privileged operation (e.g. directly querying the production database for an incident investigation). Instead of holding a permanent production credential, they request a JIT grant with a stated purpose; the request is reviewed and approved by a peer; the platform issues a short-lived credential valid for a bounded window; the engineer uses it; every action taken with the credential is recorded in the grant's usage audit; the credential is automatically revoked at expiry. No long-lived privileged credentials exist on engineer laptops.

**Why this priority**: JIT credentials dramatically reduce the standing blast radius of insider compromise. P2 alongside US3 because both address credential hygiene; rotation addresses service credentials while JIT addresses human credentials.

**Independent Test**: An engineer requests a 30-minute JIT grant for the operation `db:prod:read`. A second engineer approves it. The requester uses the credential to query a test resource; the platform records the query in the grant's `usage_audit`. After 30 minutes, the credential is revoked; a subsequent request with the credential returns 401 with an audit entry. The peer's approval and the requester's usage are both in the audit chain.

**Acceptance Scenarios**:

1. **Given** an engineer needs a privileged credential, **When** they submit a JIT request with a stated purpose, **Then** the request is queued for approval and a notification is sent to configured approvers.
2. **Given** a pending JIT request, **When** an approver reviews and approves it, **Then** a short-lived credential is issued to the requester with the requested expiry (capped by policy maximum).
3. **Given** a JIT credential is in use, **When** the holder performs an action with it, **Then** the action is recorded in the grant's usage audit with timestamp, operation, and target.
4. **Given** a JIT credential has expired, **When** any service receives a request authenticating with it, **Then** the request is rejected with 401; no extension without a new grant request is possible.
5. **Given** a security event requires immediate revocation, **When** an admin revokes the grant, **Then** the credential stops working on the next request and the revocation is audit-logged.

---

### User Story 5 — Security officer tracks a penetration test from scheduling to remediation (Priority: P3)

A security officer schedules a penetration test for the next quarter, picks a firm, receives the firm's report, imports the findings into the platform, assigns severity-appropriate remediation due dates to each finding, tracks remediation progress, and produces a report showing all findings and their resolution state. Findings beyond their due date surface in dashboards; the officer can export a pentest history for external audit.

**Why this priority**: Pentest tracking is regulatory hygiene. P3 because pentests are periodic (quarterly or annual) rather than continuous; the platform can run without this feature and only loses visibility into a once-per-quarter workflow.

**Independent Test**: Schedule a pentest. Import three stub findings (one `critical`, one `medium`, one `low`). Verify remediation due dates are assigned per the severity policy. Advance the clock past the `critical` finding's due date; verify it surfaces in the "overdue" listing. Mark the finding remediated; verify it leaves the overdue listing and appears in the remediation history.

**Acceptance Scenarios**:

1. **Given** a scheduled pentest date, **When** the date arrives, **Then** the platform flags the pentest as ready for execution and assigns an ID that can be referenced by imported findings.
2. **Given** a pentest firm delivers a report, **When** the officer imports findings, **Then** each finding is recorded with severity, title, description, and a computed remediation due date based on the severity policy.
3. **Given** a finding exists, **When** the due date passes without remediation, **Then** the finding appears in an overdue listing and emits a notification.
4. **Given** all findings from a pentest are remediated, **When** the officer queries the pentest history, **Then** it shows the pentest as complete with the remediation timeline for each finding.
5. **Given** an auditor requests pentest evidence for the past year, **When** the officer exports the history, **Then** the export includes every pentest's schedule, firm, report reference, and full finding + remediation chain.

---

### User Story 6 — Compliance auditor collects evidence against a named framework (Priority: P3)

A compliance auditor preparing for an annual SOC2 Type II assessment selects the SOC2 framework in the admin surface, sees every SOC2 control the platform is expected to demonstrate, and for each control the platform shows the automatically-collected evidence (SBOM reference, vulnerability scan results, audit chain integrity attestations, secret rotation log, JIT grant log, pentest findings). Missing controls are flagged with suggested evidence sources. The auditor can export the complete package as a signed bundle for the assessor.

**Why this priority**: Compliance evidence substrate is the final value-add of this feature — it consolidates everything produced by US1–US5 into the format assessors consume. P3 because it adds no new primitive capability; it's a curation layer on top of the other user stories. Required for credible "we can pass an assessment without a quarter of manual evidence collection" claims.

**Independent Test**: Seed the SOC2 control catalogue. Run through the operations US1–US5 produce (release with SBOM, audit event, rotation, JIT grant, pentest import). Query the SOC2 framework view; verify each control shows the evidence collected from the earlier operations. Export the bundle; verify it includes references to every evidence source with verifiable hashes.

**Acceptance Scenarios**:

1. **Given** a supported compliance framework (SOC2, ISO27001, HIPAA, PCI-DSS), **When** an auditor selects it, **Then** the platform lists every expected control with its description and evidence requirements.
2. **Given** an evidence-producing operation has occurred (SBOM generation, scan, rotation, JIT issuance, pentest import), **When** the operation completes, **Then** the platform automatically associates the output with the applicable control(s) per the evidence-requirement mapping.
3. **Given** a control has no collected evidence, **When** the auditor views the control, **Then** the platform flags the gap and suggests the operation that would satisfy it.
4. **Given** the auditor requests an evidence bundle, **When** the export runs, **Then** a signed archive is produced containing JSON pointers to every evidence item, the content hashes, and the signing key's public certificate.
5. **Given** the auditor shares the bundle with an external assessor, **When** the assessor re-verifies the hashes, **Then** every hash matches the platform-computed value, proving the bundle was produced by the platform and has not been altered.

---

### Edge Cases

- **Vulnerability scan of the scanner itself**: Scanner container images are themselves scanned for vulnerabilities; findings in scanners do not gate platform releases but are surfaced for operator review.
- **Scan database staleness**: Scanners use CVE databases that lag public disclosure by hours or days; the gate accounts for this by re-running scans on a weekly cadence against previously-published releases and surfacing newly-flagged CVEs as operator notifications (not retroactive blockers).
- **Pre-accepted exceptions**: A critical CVE with a documented exception (time-bounded, justified, approved) does not block the release but appears in every compliance export until the exception expires.
- **Secret rotation during incident**: If a rotation is in flight when an incident requires emergency rotation, the in-flight rotation is aborted and the emergency rotation supersedes it; the abort is audit-logged with reason.
- **JIT grant approver conflict of interest**: The requester and approver cannot be the same person, and platform administrators cannot approve their own JIT requests; enforced server-side (constitution rule 33 — 2PA).
- **Audit chain contains an event whose target was deleted (RTBF cascade)**: The chain entry persists; the referenced audit event's payload fields that pointed to deleted user data are replaced with tombstone references, preserving chain integrity while honouring deletion (constitution AD-17).
- **Pentest firm delivers a report with findings but no severity**: The import rejects the report with a clear message; the officer must normalise severity before re-importing.
- **Framework control with no automatic evidence source**: Surfaces as a "manual attestation required" gap with a free-text evidence-upload slot (compliance officers commonly face controls like "written policy X exists" that must be uploaded).
- **SBOM contains a component with no known version**: The SBOM records `version: "UNKNOWN"` and the vulnerability scan flags it for manual review; the release is not blocked on missing-version alone unless also flagged by a severity rule.
- **Two concurrent integrity-check runs on the audit chain**: The second run waits or receives the first run's cached result (integrity-check is read-only and deterministic — no correctness issue; wait-or-share is a throughput optimisation).
- **Audit chain grows beyond manageable size**: The chain is indexed; integrity-checks are scoped to time windows by default, with a full-chain option for periodic external attestations.

## Requirements *(mandatory)*

### Functional Requirements

**Software Bill of Materials (SBOM)**

- **FR-001**: On every tagged platform release, the CI pipeline MUST generate an SBOM in both SPDX and CycloneDX formats covering container images, Python dependencies, JavaScript dependencies, Go modules, and application source.
- **FR-002**: Every generated SBOM MUST be persisted by the platform's security-compliance store with the release version, format, content, and generation timestamp.
- **FR-003**: Every generated SBOM MUST be attached to the corresponding release artefact (e.g. GitHub release) so it is retrievable by downstream consumers without platform access.
- **FR-004**: The platform MUST expose a query surface for retrieving any release's SBOM by release version + format; the response MUST include a SHA-256 of the content for integrity verification.

**Vulnerability scanning + release gating**

- **FR-005**: The CI pipeline MUST run a defined set of vulnerability scanners (container, Python, Go, JavaScript, SAST) against every release candidate and persist each scanner's structured output.
- **FR-006**: The platform MUST support per-scanner and per-severity gating rules configured by a security officer; the rule engine determines whether a release is `passed` or `blocked`.
- **FR-007**: A release MUST be blocked when any gating rule matches — typically: any `critical` CVE in a runtime dependency without a documented exception.
- **FR-008**: A release MAY proceed when every scanner passes OR when matching findings have valid, non-expired exceptions documented in the exception registry.
- **FR-009**: Every vulnerability scan result MUST be persisted with the scanner name, release version, full findings, maximum severity, scan timestamp, and gating outcome.

**Penetration test tracking**

- **FR-010**: The platform MUST support scheduling pentests against a date, recording the commissioning firm, execution timestamp, report URL, and a signed attestation hash.
- **FR-011**: Each pentest MUST support importing its findings with severity, title, description, and a computed remediation due date based on a severity-to-SLA mapping.
- **FR-012**: Findings past their remediation due date MUST be surfaced in an overdue listing and emit a notification to the configured security-officer recipients.
- **FR-013**: Findings MUST be closeable by recording the remediation timestamp and any remediation notes; closed findings MUST remain visible in historical reports.
- **FR-014**: The platform MUST support exporting pentest history for a configurable time range, including all findings and their remediation chains.

**Automated secret rotation**

- **FR-015**: The platform MUST support scheduled rotation of named secrets with a per-secret configurable rotation interval (default 90 days).
- **FR-016**: Before the scheduled rotation date, the platform MUST begin a dual-credential window: a new credential is provisioned and both old and new credentials are valid for a configurable overlap period.
- **FR-017**: During the dual-credential overlap, every validating service MUST accept either credential; this behaviour is a contract with downstream services.
- **FR-018**: After the overlap window, the platform MUST revoke the old credential and update the schedule's `last_rotated_at` and `next_rotation_at`.
- **FR-019**: A security officer MUST be able to trigger emergency rotation on demand; emergency rotation MAY optionally skip the overlap window with explicit acknowledgment and a required reason.
- **FR-020**: Every rotation stage (initiated, overlap began, overlap ended, old revoked, completed) MUST produce an audit chain entry.
- **FR-021**: During a rotation, zero authentication failures attributable to the rotation may occur under normal load.

**Just-in-Time (JIT) credentials**

- **FR-022**: A user MUST be able to request a JIT credential grant by specifying the operation, a stated purpose, and a desired expiry (capped by policy).
- **FR-023**: A JIT grant request MUST require approval by a peer who is not the requester and not a platform administrator approving their own request (constitution rule 33).
- **FR-024**: An approved JIT grant MUST issue a short-lived credential valid until its expiry timestamp; the credential MUST be rejected by all services after expiry.
- **FR-025**: Every action taken with a JIT credential MUST be recorded in the grant's usage audit with operation, target, and timestamp.
- **FR-026**: A platform administrator MUST be able to revoke an active JIT grant at any time; revocation takes effect on the next request.
- **FR-027**: JIT grants MUST never be extendable; expired grants require a fresh approval cycle.

**Cryptographic audit chain**

- **FR-028**: Every audit event written by any bounded context MUST result in a corresponding entry in the cryptographic audit chain with a deterministic hash linking to the previous entry.
- **FR-029**: The audit chain MUST be monotonically sequenced; entry insertion MUST use a globally ordered sequence number.
- **FR-030**: The platform MUST expose an integrity-check operation that walks the chain for a given time window or the full chain, recomputes every entry's hash, and reports `valid` or `invalid` plus the sequence number of the first broken link.
- **FR-031**: The platform MUST support producing a signed attestation covering a time window, containing the start and end sequence numbers, the boundary hashes, and a cryptographic signature verifiable against a published public key.
- **FR-032**: Direct database mutation of audit chain entries MUST be detectable by the integrity-check operation (chain construction makes it so).
- **FR-033**: When an audit chain entry references an audit event whose target has been deleted via RTBF cascade, the chain entry itself MUST be preserved; referenced payload fields MUST be replaced with tombstone references (per constitution AD-17).

**Compliance evidence substrate**

- **FR-034**: The platform MUST support seeding a catalogue of compliance controls per named framework (SOC2, ISO27001, HIPAA, PCI-DSS), with each control's ID, description, and evidence requirements.
- **FR-035**: When an evidence-producing operation occurs (SBOM generation, scan, rotation, JIT grant, pentest finding, audit integrity attestation), the platform MUST automatically associate the output with every applicable control per a declared mapping.
- **FR-036**: The platform MUST expose a view that, for a selected framework, lists every control with its collected evidence and flags controls with no evidence as gaps.
- **FR-037**: The platform MUST support exporting a signed evidence bundle for a selected framework and time window; the bundle MUST include evidence pointers, content hashes, and the signing key's public certificate.
- **FR-038**: A compliance officer MUST be able to upload manual attestations (PDFs, written policies) as evidence for controls that have no automatic evidence source.

### Key Entities *(include if feature involves data)*

- **Software Bill of Materials (SBOM)** — a per-release cryptographically-hashable document in either SPDX or CycloneDX format enumerating every component in that release.
- **Vulnerability Scan Result** — a structured finding set from a single scanner run against a release candidate, with a computed maximum severity and gating outcome (`passed` or `blocked`).
- **Vulnerability Exception** — a time-bounded, justified, approved exception that allows a specific finding to pass the gating rule; expires automatically.
- **Penetration Test** — a scheduled security assessment with commissioning details, execution record, delivered report, and an attestation hash.
- **Pentest Finding** — a single vulnerability identified during a pentest, with severity, description, remediation due date, remediation status, and optional remediation notes.
- **Secret Rotation Schedule** — a per-secret configuration with rotation interval, last and next rotation timestamps, and dual-credential overlap length.
- **JIT Credential Grant** — a time-bounded, peer-approved elevation of privilege for a specific user + operation + purpose, with full usage audit.
- **Audit Chain Entry** — a single link in the cryptographic audit chain, containing a sequence number, previous-hash reference, entry hash, and reference to the underlying audit event.
- **Audit Attestation** — a signed document asserting that a specific range of the audit chain is intact, suitable for presentation to an external assessor.
- **Compliance Framework** — a named security/privacy standard (SOC2, ISO27001, HIPAA, PCI-DSS) with an expected set of controls.
- **Compliance Control** — a single numbered requirement within a framework (e.g. SOC2 CC6.1) with a description and a declared evidence-requirement specification.
- **Compliance Evidence** — a typed pointer to a stored artefact (SBOM, scan result, attestation, rotation log, JIT grant, pentest finding, manual upload) that satisfies a control, captured at collection time.
- **Evidence Bundle** — a signed archive aggregating all evidence for a selected framework + time window for external assessor handoff.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of tagged platform releases produce both an SPDX and a CycloneDX SBOM, attached to the release within the CI pipeline run itself. Verified by a periodic audit of release artefacts.
- **SC-002**: 100% of release candidates run the full scanner matrix before publication; any release that skipped a scanner is blocked automatically.
- **SC-003**: A release candidate containing a critical CVE in a runtime dependency without an exception is blocked in 100% of attempts (no false-pass rate).
- **SC-004**: An auditor requesting the SBOM + scan report for any release of the last 12 months receives the complete artefact set within 1 minute of the query.
- **SC-005**: An integrity check on the entire audit chain completes in under 60 seconds per 1 million entries on a reference instance, returning a definitive `valid` or `invalid` result with the offending sequence number.
- **SC-006**: When a database operator tampers with an audit entry out of band, the next integrity check detects it within the same run (zero false-negative).
- **SC-007**: During a production credential rotation under nominal load (100 req/s), the count of authentication failures directly attributable to the rotation is zero in ≥ 99% of rotations.
- **SC-008**: 100% of JIT credential grants carry a usage audit showing every operation performed with the credential; grants with no usage audit trigger a compliance finding within 24 hours of issuance.
- **SC-009**: 100% of pentest findings past their remediation due date appear in the overdue listing within 15 minutes of the due date passing.
- **SC-010**: A compliance officer can produce a signed SOC2 evidence bundle covering the past 90 days in under 5 minutes, and the bundle's hashes verify against platform-computed values on an independent client (demonstrating the bundle is tamper-evident).
- **SC-011**: Every privileged action on the platform (secret rotation stage transition, JIT grant, approval, revocation, pentest import, manual evidence upload) is both audit-logged AND represented in the audit chain within 5 seconds of the action.

## Assumptions

- The platform's existing audit bounded context will be extended (not replaced) to write each audit event into the new cryptographic chain; existing audit emitters continue to use the familiar `publish_*_event` pattern.
- The vulnerability scanner matrix includes at minimum: container image scanner (e.g. Trivy or Grype), Python dependency scanner (e.g. `pip-audit`), Go module scanner (e.g. `govulncheck`), JavaScript scanner (e.g. `npm audit`), and at least one SAST engine (e.g. Bandit or gosec). Specific tool choices are deferred to the plan and may evolve; the gating contract is tool-agnostic.
- The platform ships with a default severity-to-SLA mapping for pentest findings (e.g. critical: 7 days, high: 30 days, medium: 90 days, low: 180 days). Operators can override at install time but not narrow below the default.
- Compliance control catalogues for SOC2 CC-series, ISO 27001:2022 Annex A, HIPAA Security Rule, and PCI-DSS v4.0 ship as seed data; other frameworks (FedRAMP, NIST CSF, etc.) are future work.
- The audit chain signing key lives in the existing secret-storage layer (Vault or its transitional fallback per UPD-040); rotation of the signing key itself is a deliberate governance event requiring explicit approval and a full attestation-key changeover protocol.
- Manual evidence uploads (PDFs, written policies) are stored in the platform's S3-compatible object store under a `compliance-evidence/` bucket with access control limited to compliance officers.
- "Zero-downtime rotation" applies to services that correctly implement the dual-credential validation contract; services that hold-and-cache credentials without refresh will still see failures. A separate operational checklist identifies which services have adopted the contract.
- JIT grants have a hard maximum expiry of 24 hours; policy can narrow this per operation but not widen it without a constitutional amendment.
- The approver pool for a given JIT operation is configured by a platform admin; the set may be role-based (e.g. "any user with the `incident_responder` role") rather than per-individual.
- A pentest's `attestation_hash` is computed by hashing the firm-delivered report (PDF) plus the pentest's metadata; the hash is persisted at import time and verified on export.
- Exceptions to vulnerability gating rules are themselves audit chain entries — creating an exception requires approval and the approval link is preserved indefinitely.
- Retention of audit chain entries matches the platform's broader audit-retention policy (inherited from the audit BC). Entries are never pruned under normal operation; a compliance-reviewed archival process may move very old entries to cold storage while preserving chain continuity.
