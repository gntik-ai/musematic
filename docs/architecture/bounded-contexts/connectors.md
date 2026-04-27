# Connectors

Connectors owns connector types, instances, credentials, routes, inbound or outbound delivery, and dead-letter handling.

Primary entities include connector type definitions, connector instances, credential references, routes, delivery rows, and dead-letter entries. REST APIs manage connector configuration and diagnostics. Events support delivery and audit workflows.

Connectors should keep provider credentials as secret references and make delivery idempotent.
