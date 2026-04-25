# Privacy Compliance

Feature 076 adds the backend privacy controls required for GDPR/CCPA operations:
data-subject requests, deletion tombstones, consent records, privacy impact
assessments, DLP rules/events, and workspace residency policy.

The implementation exposes admin endpoints under `/api/v1/privacy/*` and
self-service endpoints under `/api/v1/me/dsr` and `/api/v1/me/consents`.
Erasure requests run through the privacy cascade adapters and produce immutable
tombstones whose proof hash is externally verifiable.

Operational switches:

- `FEATURE_PRIVACY_DSR_ENABLED` gates self-service DSR flows and workers.
- `FEATURE_DLP_ENABLED` enables DLP scanning at policy and guardrail insertion points.
- `FEATURE_RESIDENCY_ENFORCEMENT` enables request-time residency checks.

