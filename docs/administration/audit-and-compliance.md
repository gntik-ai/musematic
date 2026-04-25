# Audit And Compliance

Privacy compliance records are linked to the platform audit chain by event type.
DSR lifecycle transitions, deletion cascades, PIA transitions, DLP events,
residency changes, residency violations, and consent revocations all emit typed
privacy events.

Primary operator surfaces:

- `/api/v1/privacy/dsr` for data-subject requests and tombstone export.
- `/api/v1/privacy/pia` for privacy impact assessments and approval workflow.
- `/api/v1/privacy/dlp/rules` and `/api/v1/privacy/dlp/events` for DLP operations.
- `/api/v1/privacy/residency/{workspace_id}` for regional policy configuration.
- `/api/v1/privacy/consents?user_id=` for consent history review.

Signed deletion tombstones can be verified without platform imports using
`tests/e2e/scripts/verify_signed_tombstone.py`.

