# TLS Strategy

FR-614 uses Let's Encrypt DNS-01 wildcard certificates managed by cert-manager. Production hosts should terminate TLS at the ingress or load balancer, with internal service traffic protected by Kubernetes network boundaries and service credentials.

## Standard Renewal

1. cert-manager renews certificates before expiry.
2. DNS-01 challenges update the authoritative DNS provider.
3. Alerts fire when renewal fails, expiry approaches, or challenge resources remain stuck.
4. Operators verify `app.musematic.ai`, `api.musematic.ai`, and `grafana.musematic.ai`.

## Emergency Renewal

Use the [TLS Emergency Renewal runbook](../operator-guide/runbooks/tls-emergency-renewal.md) when automation fails. Manual certificate import is temporary and must be followed by restoring cert-manager automation.
