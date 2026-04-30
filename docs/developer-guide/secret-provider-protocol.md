# Secret Provider Protocol

All platform secret reads and writes go through `platform.common.secret_provider.SecretProvider`.

## Surface

```python
class SecretProvider(Protocol):
    async def get(path: str, key: str = "value", *, critical: bool = False) -> str: ...
    async def put(path: str, values: dict[str, str]) -> None: ...
    async def delete_version(path: str, version: int) -> None: ...
    async def list_versions(path: str) -> list[int]: ...
    async def health_check() -> HealthStatus: ...
```

`flush_cache(path: str | None = None) -> int` is available for admin operations.

## Modes

- `mock`: local `.vault-secrets.json` plus the legacy `CONNECTOR_SECRET_*` fallback.
- `kubernetes`: transitional backend using Kubernetes Secrets derived from the canonical path.
- `vault`: production backend using HashiCorp Vault KV v2.

## Errors

- `CredentialUnavailableError`: secret missing, backend unavailable, or critical cache miss.
- `CredentialPolicyDeniedError`: Vault policy denies the read or write.
- `InvalidVaultPathError`: the path does not match the canonical scheme.

## Critical Reads

Use `critical=True` for login, OAuth callbacks, IBOR sync, and other flows where stale or missing credentials must fail closed.

```python
secret = await secret_provider.get(
    "secret/data/musematic/production/oauth/google",
    "client_secret",
    critical=True,
)
```

Never call `os.getenv()` for secret-pattern names outside the provider implementation.
