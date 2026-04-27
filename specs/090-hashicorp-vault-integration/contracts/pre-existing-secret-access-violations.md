# Pre-Existing Secret Access Violations — UPD-040

Date: 2026-04-27

Command:

```bash
python scripts/check-secret-access.py
```

Result: exit code `1`.

## Findings

These findings were present in the brownfield code path before UPD-040's Track A rewires are complete. They are not introduced by the new `SecretProvider` module or Go mirror.

| File | Line | Finding |
| --- | ---: | --- |
| `apps/control-plane/src/platform/connectors/service.py` | 748 | Direct `VaultResolver.resolve()` call during connector runtime-config materialization. |
| `apps/control-plane/src/platform/admin/bootstrap.py` | 261 | Direct read of `PLATFORM_SUPERADMIN_PASSWORD`. |
| `apps/control-plane/src/platform/security_compliance/providers/rotatable_secret_provider.py` | 70 | Direct `VaultResolver.resolve()` call in the rotation provider. |
| `apps/control-plane/src/platform/common/clients/redis.py` | 76 | Direct read of `REDIS_PASSWORD`. |
| `services/reasoning-engine/pkg/persistence/redis.go` | 19 | Direct read of `REDIS_PASSWORD`. |
| `services/runtime-controller/pkg/config/config.go` | 43 | Direct read of `REDIS_PASSWORD`. |

## Follow-Up

- The connector runtime and rotation-provider findings are in UPD-040 Track A scope and should be removed as those callsites move to `SecretProvider`.
- The super-admin bootstrap finding belongs to the Rule 31 bootstrap-secret review path. It should be handled with the admin bootstrap hardening work so the generated/loaded value is never logged and is not read through arbitrary callsites.
- The Redis password findings should move to structured settings or a transitional `SecretProvider` path in a follow-up hardening change. They are infrastructure credentials and should not be exempted silently.
- The CI job in T025 should be enabled once these baseline items are either fixed or explicitly accepted through a temporary baseline mechanism.
