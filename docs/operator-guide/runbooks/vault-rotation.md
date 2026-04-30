# Vault Secret Rotation

## Symptom

A Vault-backed credential is scheduled for rotation or suspected exposed.

## Diagnosis

Identify the canonical path, owning bounded context, and whether it is handled by `RotatableSecretProvider`.

## Remediation

1. Write the new value as a new KV v2 version.
2. Keep both prior and new versions readable for the dual-credential window.
3. Flush affected caches:

```bash
platform-cli vault flush-cache --all-pods
```

4. After the overlap window, destroy the prior KV version.

## Verification

Confirm new reads succeed, old reads fail after the window, and the audit chain contains only path/version metadata.

## Rollback

If the prior version is still inside the overlap window, pin consumers back to it and flush caches. If destroyed, restore from Vault backup or re-enter the prior credential through the normal secret-entry process.
