# Incident Response

Incident Response owns incident integrations, incidents, runbooks, post-mortems, external alert references, deduplication, and retry state.

Primary entities include integrations, incidents, runbooks, post-mortems, and external alerts. REST APIs manage integrations, incidents, and runbooks. Redis stores deduplication and delivery retry keys.

Incident triggers should use `IncidentTriggerInterface`; parallel alert ingestion paths should not be added.
