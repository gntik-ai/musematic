# OAuth Secret Rotation

## Symptom

An OAuth client secret is expiring, exposed, or scheduled for rotation.

## Diagnosis

Identify the provider in `/admin/settings?tab=oauth`, confirm the current Vault path, and check whether active login traffic is using the provider. Rotation writes a new Vault KV v2 version and does not return the new value in any response.

## Remediation

Preferred path:

1. Open the OAuth provider in the admin settings tab.
2. Select rotate secret.
3. Paste the new upstream OAuth client secret into the write-only field.
4. Submit the rotation.
5. Confirm the action returns `204 No Content`.

CLI fallback for stale Vault credentials:

```bash
platform-cli vault rotate-token --pod control-plane-api-0
platform-cli vault flush-cache --all-pods
```

The OAuth rotation action itself is provider-scoped and writes through the control-plane API.

## Verification

Confirm Vault KV v2 has a new version at `secret/data/musematic/{environment}/oauth/{provider}/client-secret`, cache flush succeeds, and audit history contains `auth.oauth.secret_rotated` with `changed_fields=["client_secret"]`.

Run a provider connectivity test from the admin tab. The diagnostic result may show redirect or upstream validation errors, but it must never include the secret value.

## Rollback

If the upstream provider still accepts the previous value, roll back by writing the previous KV v2 version as a new version and flushing the control-plane cache. If the secret was exposed, revoke it upstream instead of rolling back.
