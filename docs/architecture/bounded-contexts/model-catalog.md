# Model Catalog

Model Catalog owns model entries, approvals, provider credentials, fallback chains, routing policy, and model card pre-flight checks.

Primary entities include catalog entries, model cards, provider credentials, approval expiry, and fallback policy. REST APIs manage model catalog state. Runtime clients resolve model choices through the model router.

Model fallback supports graceful degradation while preserving policy enforcement and auditability.
