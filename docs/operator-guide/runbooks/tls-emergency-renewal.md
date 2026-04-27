# TLS Emergency Renewal

## Symptom

Certificate auto-renewal fails or a production certificate is near expiry.

## Diagnosis

Check cert-manager Certificate and Challenge resources, DNS-01 provider logs, Let's Encrypt rate limits, and the wildcard DNS zone.

## Remediation

Fix DNS credentials or challenge records, force renewal through cert-manager, and only use manual certificate import as a temporary emergency measure. Keep the canonical TLS strategy in [TLS Strategy](../../configuration/tls-strategy.md) aligned with the change.

## Verification

Confirm `app.musematic.ai`, `api.musematic.ai`, and `grafana.musematic.ai` present the renewed certificate chain and that expiry alerts clear.
