# Vault Token Rotation

## Symptom

An operator suspects a Vault client token has leaked, was revoked, or is close to expiry.

## Diagnosis

Use the fallback status command:

```bash
platform-cli vault status
```

Review `auth_method`, token expiry timestamp, lease count, and recent failures.

## Remediation

Force immediate renewal or reauthentication on the target process:

```bash
platform-cli vault rotate-token --pod control-plane-api-0
```

For a wider incident, repeat per control-plane pod and then rotate the Kubernetes auth role or AppRole SecretID at the Vault layer.

## Verification

Run `platform-cli vault status` again and confirm token expiry moved forward and renewal failures are not increasing.

## Rollback

There is no token rollback. Restore service by fixing the auth role, projected ServiceAccount token, AppRole SecretID, or Vault policy, then force rotation again.
