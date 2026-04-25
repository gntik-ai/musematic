# Specification Quality Checklist: Privacy Compliance (GDPR / CCPA)

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-04-25
**Feature**: [spec.md](../spec.md)

## Content Quality

- [X] No implementation details (languages, frameworks, APIs) — *technical terms (GDPR Article 17, CCPA §1798.105, Ed25519, SHA-256, regex, JSONB) appear because they are the industry/regulatory-standard vocabulary a privacy-officer / compliance-assessor audience works in; specific files and table names from the user input (cascade_deletion.py, dsr_service.py, dlp_rules table) do not appear in the FRs — they stay at the plan level*
- [X] Focused on user value and business needs — *six user stories grounded in real personas (data subject, end-user, privacy officer, workspace admin, compliance auditor); each maps to a concrete compliance outcome (GDPR Article 17, AI disclosure under EU AI Act, DPIA, residency, DLP, external attestation)*
- [X] Written for non-technical stakeholders — *each technical term is contextualised in a legal or operational story; the regulatory framing (GDPR Article references, CCPA §references) is the appropriate vocabulary for this audience*
- [X] All mandatory sections completed — *User Scenarios, Requirements, Success Criteria, Assumptions all substantive*

## Requirement Completeness

- [X] No [NEEDS CLARIFICATION] markers remain — *reasonable defaults chosen and documented: tombstone never contains PII, 24-hour optional hold on erasure, DLP match_summary is classification label only, 90-day DLP event retention, seed pattern set, indefinite tombstone retention*
- [X] Requirements are testable and unambiguous — *FR-001 through FR-031 each describe observable outcomes; FR-005 (every data store cascaded), FR-007 (tombstone payload contents), FR-013 (residency rejection at query time), FR-023 (certification blocked without PIA) all concretely verifiable*
- [X] Success criteria are measurable — *SC-001–SC-011 have numeric thresholds (1-hour post-completion scan, 5-minute external verify, 15-minute cascade perf, < 5-second audit propagation) or observable Booleans (100% blocked, zero rows remaining, zero false-passes)*
- [X] Success criteria are technology-agnostic — *criteria describe compliance outcomes, hash/signature verification results, propagation latencies, audit completeness; no library / framework / DB-specific language*
- [X] All acceptance scenarios are defined — *US1 × 6, US2 × 5, US3 × 5, US4 × 5, US5 × 5, US6 × 5 = 31 Given/When/Then scenarios covering every FR*
- [X] Edge cases are identified — *twelve edge cases covering new-store detection, partial cascade failure, third-party mentions in access DSR, creator erasure (agent disownment), residency removal, high-match DLP noise, PIA invalidation, in-flight training + revocation, unknown region fail-closed, post-erasure tombstone lookup, automated-workflow consent bypass, DSR by legal representative*
- [X] Scope is clearly bounded — *Assumptions explicitly exclude: in-transit encryption (TLS handled elsewhere), PIA templates (future), i18n of disclosure (ties to UPD-030), non-user third parties (access-DSR redaction only). Out-of-scope items are named*
- [X] Dependencies and assumptions identified — *UPD-024 dependency load-bearing for audit chain + signing key; UPD-016 accounts dependency for user states; UPD-030 i18n dependency for localised disclosure (future). Env-var fallback during UPD-024 rollout explicitly accepted*

## Feature Readiness

- [X] All functional requirements have clear acceptance criteria — *FR-001–FR-004 DSR → US1 scenarios 1, 4, 6; FR-005–FR-011 cascade + tombstone → US1 scenarios 2, 3, 5 + US6; FR-012–FR-016 residency → US4 all scenarios; FR-017–FR-021 DLP → US5 all scenarios; FR-022–FR-026 PIA → US3 all scenarios; FR-027–FR-031 consent → US2 all scenarios*
- [X] User scenarios cover primary flows — *six primary flows (exercise right, disclose+consent, assess agent, enforce region, detect leak, verify externally) cover the complete GDPR/CCPA surface*
- [X] Feature meets measurable outcomes defined in Success Criteria — *every SC maps to one or more FRs and at least one acceptance scenario; SC-001 ↔ FR-007 + US1 #3; SC-002 ↔ FR-005 + US1 #2; SC-004 ↔ FR-011 + US6; etc.*
- [X] No implementation details leak into specification — *no Pydantic, SQLAlchemy, FastAPI, specific SDK names in FRs; user-input DDL stays at the plan level*

## Notes

- All items pass on first iteration. Ready for `/speckit.plan`.
- User-input contained DDL for 7 tables, specific file paths, and a list of modified files. These were treated as plan-level implementation guidance and translated into FRs speaking to observable compliance behaviours.
- Constitution v1.3.0 alignment called out in the spec:
  - **Rule 15** (every data deletion cascades) — FR-005
  - **Rule 16** (every DSR produces a tombstone) — FR-006 + FR-007 + FR-008
  - **Rule 18** (regional queries enforce data residency) — FR-013 (query time, not install time)
  - **Rule 9** (every PII operation emits audit chain entry) — FR-003 + FR-014 + FR-026
  - **Rule 33** (2PA server-side) — FR-024 (PIA approver cannot self-approve)
  - **AD-17** (tombstone-based RTBF proof) — FR-008 + FR-011 (tombstones never contain PII; signed for external verification)
- **UPD-024 dependency** load-bearing for: audit chain entries (FR-003, FR-014, FR-026), Ed25519 signing for tombstone attestation (FR-011). Spec explicitly accepts UPD-024's env-var fallback during its rollout.
- **US1 (erasure) is the MVP** — without erasure + tombstone proof the feature has no compliance claim. US2 (consent) is P1 because it's legally required and trivially implementable once US1 lands. US3–US6 layer on as the platform matures.
- New Kafka topics from constitution §7 enumerated: `privacy.dsr.received`, `privacy.dsr.completed`, `privacy.deletion.cascaded`, `privacy.dlp.event`, `privacy.pia.approved`. Subsequent FRs reference them correctly.
