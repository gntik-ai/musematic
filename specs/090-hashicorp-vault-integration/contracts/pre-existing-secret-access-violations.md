# Pre-Existing Secret Access Violations — UPD-040

Date: 2026-04-30

Command:

```bash
python scripts/check-secret-access.py
```

Result after Track A rewires: exit code `0`.

The checker keeps a temporary baseline for pre-existing infrastructure/bootstrap reads so CI can fail on new violations introduced after UPD-040 while those older findings are handled by their owning hardening tracks.

## Findings

These findings were present in the brownfield code path before UPD-040's Track A rewires are complete. They are not introduced by the new `SecretProvider` module or Go mirror.

| File | Line | Finding |
| --- | ---: | --- |
| `apps/control-plane/src/platform/admin/bootstrap.py` | 264 | Direct read of `PLATFORM_SUPERADMIN_PASSWORD` (temporarily baselined in `scripts/check-secret-access.py`). |
| `apps/control-plane/src/platform/common/clients/redis.py` | 76 | Direct read of `REDIS_PASSWORD`. |
| `services/reasoning-engine/pkg/persistence/redis.go` | 19 | Direct read of `REDIS_PASSWORD`. |
| `services/runtime-controller/pkg/config/config.go` | 43 | Direct read of `REDIS_PASSWORD`. |

## Follow-Up

- The connector runtime and rotation-provider findings from the 2026-04-27 baseline have been removed from this report; rotation now flows through `SecretProvider`, and direct `VaultResolver.resolve()` calls are blocked by the checker.
- The super-admin bootstrap finding belongs to the Rule 31 bootstrap-secret review path. It should be handled with the admin bootstrap hardening work so the generated/loaded value is never logged and is not read through arbitrary callsites.
- The Redis password findings should move to structured settings or a transitional `SecretProvider` path in a follow-up hardening change. They are infrastructure credentials and should not be exempted silently.
- The temporary baseline must be removed when the owning hardening work rewires these remaining reads.
