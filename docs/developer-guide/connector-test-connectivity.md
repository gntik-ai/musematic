# Connector Test Connectivity

Connector implementations expose `test_connectivity(config, credential_refs)` for dry-run validation before workspace owners activate delivery.

## Uniform Result

Each implementation returns:

```python
TestResult(success: bool, diagnostic: str, latency_ms: float)
```

Diagnostics should identify the failure class without echoing tokens, passwords, webhook signatures, or resolved secret values.

## Dry-Run Rules

- Slack validates with `auth.test`.
- Telegram validates with `getMe`.
- Email validates with SMTP/IMAP NOOP.
- Webhook validates reachability with `HEAD`, not `POST`.

Test-connectivity must not create `outbound_deliveries`, send a user-visible message, or write resolved credentials to logs or audit metadata.

## Adding A Connector

Implement `test_connectivity()`, scrub diagnostics with the connector secret scrubber, and add a unit test proving no delivery row is created. If the provider has no non-delivering diagnostic endpoint, expose a configuration validation result and document the limitation.
