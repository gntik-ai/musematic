# Threat Model

Musematic separates trust boundaries across browser clients, API gateway, control-plane bounded contexts, satellite runtime services, Kubernetes namespaces, data stores, external model providers, and third-party integrations.

Primary threats:

- Stolen user tokens or service account keys.
- Over-broad workspace visibility grants.
- Prompt injection that attempts tool or data exfiltration.
- Compromised webhook receivers or replayed delivery payloads.
- Provider credential leakage.
- Runtime pod breakout or unintended network egress.
- Audit evidence tampering.
- Cross-tenant data exposure through search, logs, or analytics.

Controls include MFA, RBAC, zero-trust visibility, purpose-bound authorization, policy bundles, output sanitization, network policies, secret references, signed webhook payloads, append-only audit chain entries, and evidence verification.
