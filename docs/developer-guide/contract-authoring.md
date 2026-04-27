# Contract Authoring

Contracts define stable expectations for APIs, events, workflows, and integrations.

Use OpenAPI for REST, protobuf for gRPC where available, Pydantic models for control-plane schemas, and explicit Kafka event payload classes for domain events. A contract change should document compatibility, migration behavior, and how clients should handle unknown fields.

Guidelines:

- Add fields as optional first.
- Prefer stable machine-readable error codes.
- Include correlation ID and GID where possible.
- Keep event consumers idempotent.
- Regenerate generated references and commit snapshots.
