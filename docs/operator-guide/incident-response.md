# Incident Response

Incident response is owned by the incident-response bounded context from feature 080. Incidents deduplicate by condition fingerprint, track external alert delivery state, link to runbooks, and produce post-mortem records.

## Flow

1. Confirm the incident source and deduplication key.
2. Identify affected workspace, service, region, and user impact.
3. Open the linked runbook or choose a runbook from the library.
4. Record mitigation steps and timeline notes.
5. Close the incident only after verification passes.
6. Complete the post-mortem when the incident exceeds the internal threshold.

Runbook deep links use `docs.musematic.ai/operator-guide/runbooks/{slug}`.
