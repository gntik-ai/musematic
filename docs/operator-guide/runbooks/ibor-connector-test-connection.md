# IBOR Connector Test Connection

## Symptom

A platform admin configures LDAP, OIDC, or SCIM identity-broker sync and the connector cannot pass test-connection or sync-now.

## Diagnosis

Open `/admin/settings?tab=ibor` and run the stepped diagnostic. LDAP failures usually map to one of these stages:

- `dns_lookup`: name resolution or network policy.
- `tcp_connect`: firewall, service endpoint, or port mismatch.
- `tls_handshake`: certificate trust, hostname mismatch, or protocol version.
- `ldap_bind`: credential reference, bind DN, or password.
- `sample_query`: BaseDN, filter, or attribute mapping.

Use Loki logs for the connector ID when the UI shows an error row. Diagnostics must not expose plaintext bind passwords or tokens.

## Remediation

Fix the earliest failing stage first. Rotate credentials through the secret provider if bind credentials are wrong. Update attribute mappings for Active Directory, OpenLDAP, or FreeIPA differences, then rerun the diagnostic and trigger sync-now.

## Verification

Sync history should show a new run with `succeeded` or an expected partial-success count. Confirm user and role changes appear in the auth bounded context and that the sync event is present in audit/log search.

## Rollback

Disable the connector or restore the previous credential reference. Existing users remain in their current state until a later successful sync reconciles them.
