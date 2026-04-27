# Best Practices

- Require MFA for admins and super admins.
- Use service accounts for automation and rotate keys on a schedule.
- Keep provider credentials in the secret provider, never in agent packages or Helm values committed to source.
- Enable zero-trust visibility and grant only the workspaces that need an agent.
- Keep `FEATURE_ALLOW_HTTP_WEBHOOKS=false` in production.
- Validate webhook signatures with raw request bytes and replay windows.
- Use NetworkPolicy defaults that deny unneeded egress.
- Keep audit-chain verification in regular compliance checks.
- Run vulnerability gates before release.
- Keep runbooks current and link incidents to post-mortems.
- Use GID and correlation ID in every investigation.
