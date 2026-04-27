# Structured Logging

All platform runtimes emit JSON logs to stdout with the same core contract:
`timestamp`, `level`, `service`, `bounded_context`, and `message`.

Optional correlation fields are included when available: `trace_id`, `span_id`,
`correlation_id`, `workspace_id`, `goal_id`, `user_id`, and `execution_id`.
These fields are payload fields, not Loki labels.

Allowed Loki labels are deliberately low-cardinality:
`service`, `bounded_context`, `level`, `namespace`, `pod`, and `container`.
The CI check `scripts/ci/check_loki_label_cardinality.py` fails if a
high-cardinality field is promoted in Promtail configuration.

Runtime entrypoints:

- Python: `platform.common.logging.configure_logging(service, bounded_context)`
- Go: each satellite exposes `internal/logging.Configure(service, boundedContext)`
- Web: `apps/web/lib/logging.ts` exposes `log.info`, `log.warn`, and `log.error`

Audit-chain append logging is intentionally transactional. `AuditChainService`
logs `audit.chain.appended` inside the same database transaction as the chain
row insert so an event cannot be reported as logged if the log emit fails.
