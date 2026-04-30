# Connector Self-Service Troubleshooting

## Symptom

A workspace owner cannot activate Slack, Telegram, email, or webhook delivery from `/workspaces/{id}/connectors`.

## Diagnosis

Check the connector type, credential reference, and dry-run result. Test-connectivity is intentionally non-delivering: Slack uses `auth.test`, Telegram uses `getMe`, email uses SMTP/IMAP NOOP, and webhooks use `HEAD`.

Common failures:

- Invalid credential reference or missing Vault KV v2 version.
- Provider rate-limit response such as HTTP 429.
- Webhook endpoint rejects `HEAD` or has TLS certificate errors.
- Email server accepts SMTP but rejects IMAP NOOP.

## Remediation

Rotate or repair the secret through the write-only secret flow, rerun test-connectivity, then activate. For provider rate limits, wait for the retry window and check delivery dead-letter entries before retrying user-visible delivery.

## Verification

Confirm test-connectivity returns success without creating an outbound delivery row. After activation, send a normal platform event and verify delivery appears in the connector activity panel.

## Rollback

Disable or delete the workspace connector. Preserve delivery and dead-letter rows for incident review before removing any upstream app configuration.
