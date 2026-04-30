from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import re
import signal
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from platform.connectors.exceptions import CredentialUnavailableError
from typing import Any, Literal, Protocol

try:  # pragma: no cover - exercised when the optional Vault dependency is installed
    import hvac  # type: ignore[import-untyped]
    from hvac import exceptions as hvac_exceptions
except Exception:  # pragma: no cover - keeps mock/test mode importable without hvac
    hvac = None
    hvac_exceptions = None

PromCounter: Any = None
PromGauge: Any = None
REGISTRY: Any = None
try:  # pragma: no cover - prometheus_client is present in the control-plane env
    from prometheus_client import Counter as _PromCounter
    from prometheus_client import Gauge as _PromGauge
    from prometheus_client.registry import REGISTRY as _PROM_REGISTRY

    PromCounter = _PromCounter
    PromGauge = _PromGauge
    REGISTRY = _PROM_REGISTRY
except Exception:  # pragma: no cover
    pass

CANONICAL_SECRET_PATH_RE = re.compile(
    r"^secret/data/musematic/"
    r"(production|staging|dev|test|ci)/"
    r"(oauth|model-providers|notifications|ibor|audit-chain|connectors|accounts|_internal)/"
    r"[a-zA-Z0-9_/-]+$"
)

__all__ = [
    "CredentialPolicyDeniedError",
    "CredentialUnavailableError",
    "HealthStatus",
    "InvalidVaultPathError",
    "KubernetesSecretProvider",
    "MockSecretProvider",
    "SecretProvider",
    "VaultSecretProvider",
    "k8s_secret_name_to_vault_path",
    "validate_secret_path",
    "vault_log_processor",
    "vault_path_to_k8s_secret_name",
]


@dataclass(frozen=True, slots=True)
class HealthStatus:
    status: Literal["green", "yellow", "red"]
    auth_method: str | None = None
    token_expiry_at: datetime | None = None
    lease_count: int | None = None
    recent_failures: list[str] = field(default_factory=list)
    cache_hit_rate: float = 0.0
    error: str | None = None


class CredentialPolicyDeniedError(CredentialUnavailableError):
    status_code = 403

    def __init__(self, credential_key: str) -> None:
        super().__init__(credential_key)
        self.code = "CREDENTIAL_POLICY_DENIED"


class InvalidVaultPathError(ValueError):
    def __init__(self, path: str) -> None:
        super().__init__(f"Vault path does not match the canonical KV v2 scheme: {path}")


class SecretProvider(Protocol):
    async def get(self, path: str, key: str = "value", *, critical: bool = False) -> str: ...

    async def put(self, path: str, values: dict[str, str]) -> None: ...

    async def flush_cache(self, path: str | None = None) -> int: ...

    async def delete_version(self, path: str, version: int) -> None: ...

    async def list_versions(self, path: str) -> list[int]: ...

    async def health_check(self) -> HealthStatus: ...


def validate_secret_path(path: str) -> None:
    if not CANONICAL_SECRET_PATH_RE.fullmatch(path):
        raise InvalidVaultPathError(path)


_VALID_ENVIRONMENTS = {"production", "staging", "dev", "test", "ci"}
_VALID_DOMAINS = {
    "oauth",
    "model-providers",
    "notifications",
    "ibor",
    "audit-chain",
    "connectors",
    "accounts",
    "_internal",
}
_FORBIDDEN_LOG_FIELDS = {"token", "secret_id", "kv_value", "client_secret"}


class _NoopMetric:
    def labels(self, *_args: Any, **_kwargs: Any) -> _NoopMetric:
        return self

    def inc(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def set(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _metric(factory: Any, name: str, documentation: str, labels: tuple[str, ...] = ()) -> Any:
    if factory is None or REGISTRY is None:
        return _NoopMetric()
    try:
        return factory(name, documentation, labels)
    except ValueError:
        names = getattr(REGISTRY, "_names_to_collectors", {})
        return names.get(name) or names.get(f"{name}_total") or _NoopMetric()


VAULT_LEASE_COUNT = _metric(PromGauge, "vault_lease_count", "Active Vault lease count.", ("pod",))
VAULT_TOKEN_EXPIRY_SECONDS = _metric(
    PromGauge, "vault_token_expiry_seconds", "Seconds until the current Vault token expires."
)
VAULT_RENEWAL_SUCCESS_TOTAL = _metric(
    PromCounter, "vault_renewal_success_total", "Vault token renewal successes."
)
VAULT_RENEWAL_FAILURE_TOTAL = _metric(
    PromCounter, "vault_renewal_failure_total", "Vault token renewal failures."
)
VAULT_AUTH_FAILURE_TOTAL = _metric(
    PromCounter, "vault_auth_failure_total", "Vault auth failures.", ("auth_method",)
)
VAULT_READ_TOTAL = _metric(PromCounter, "vault_read_total", "Vault secret reads.", ("domain",))
VAULT_WRITE_TOTAL = _metric(PromCounter, "vault_write_total", "Vault secret writes.", ("domain",))
VAULT_CACHE_HIT_TOTAL = _metric(PromCounter, "vault_cache_hit_total", "Vault cache hits.")
VAULT_CACHE_MISS_TOTAL = _metric(PromCounter, "vault_cache_miss_total", "Vault cache misses.")
VAULT_CACHE_HIT_RATIO = _metric(PromGauge, "vault_cache_hit_ratio", "Vault cache hit ratio.")
VAULT_SERVING_STALE_TOTAL = _metric(
    PromCounter, "vault_serving_stale_total", "Vault stale secret reads."
)
VAULT_POLICY_DENIED_TOTAL = _metric(
    PromCounter, "vault_policy_denied_total", "Vault policy denied responses.", ("path",)
)


def vault_log_processor(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    leaked = _FORBIDDEN_LOG_FIELDS.intersection(event_dict)
    if leaked:
        raise AssertionError(f"Forbidden Vault log field(s): {', '.join(sorted(leaked))}")
    return event_dict


def _domain_from_path(path: str) -> str:
    parts = path.split("/")
    return parts[4] if len(parts) > 4 else "unknown"


def _now() -> datetime:
    return datetime.now(UTC)


def vault_path_to_k8s_secret_name(path: str) -> str:
    validate_secret_path(path)
    _, _, _, environment, domain, resource = path.split("/", 5)
    return f"musematic-{environment}-{domain}-{resource.replace('/', '__')}"


def k8s_secret_name_to_vault_path(name: str) -> str:
    if not name.startswith("musematic-"):
        raise InvalidVaultPathError(name)
    remainder = name.removeprefix("musematic-")
    environment, _, rest = remainder.partition("-")
    if environment not in _VALID_ENVIRONMENTS or not rest:
        raise InvalidVaultPathError(name)
    for domain in sorted(_VALID_DOMAINS, key=len, reverse=True):
        prefix = f"{domain}-"
        if rest.startswith(prefix):
            resource = rest.removeprefix(prefix).replace("__", "/")
            path = f"secret/data/musematic/{environment}/{domain}/{resource}"
            validate_secret_path(path)
            return path
    raise InvalidVaultPathError(name)


class MockSecretProvider:
    def __init__(
        self,
        settings: Any,
        *,
        secrets_file: str | None = None,
        validate_paths: bool = True,
    ) -> None:
        self.settings = settings
        self.secrets_file = secrets_file or str(
            getattr(getattr(settings, "connectors", object()), "vault_mock_secrets_file", "")
            or ".vault-secrets.json"
        )
        self.validate_paths = validate_paths

    async def get(self, path: str, key: str = "value", *, critical: bool = False) -> str:
        del critical
        if self.validate_paths:
            validate_secret_path(path)
        return await asyncio.to_thread(self._get_sync, path, key)

    async def put(self, path: str, values: dict[str, str]) -> None:
        if self.validate_paths:
            validate_secret_path(path)
        await asyncio.to_thread(self._put_sync, path, values)

    async def flush_cache(self, path: str | None = None) -> int:
        del path
        return 0

    async def delete_version(self, path: str, version: int) -> None:
        del path, version

    async def list_versions(self, path: str) -> list[int]:
        if self.validate_paths:
            validate_secret_path(path)
        return [1]

    async def health_check(self) -> HealthStatus:
        readable = await asyncio.to_thread(self._has_readable_file)
        if readable:
            return HealthStatus(status="green", auth_method="mock")
        return HealthStatus(
            status="red",
            auth_method="mock",
            error=f"Mock secrets file is not readable: {self.secrets_file}",
        )

    def _get_sync(self, path: str, key: str) -> str:
        for candidate in self._candidate_paths():
            if not candidate.exists():
                continue
            content = json.loads(candidate.read_text(encoding="utf-8"))
            if isinstance(content, dict):
                value = content.get(path)
                if isinstance(value, str):
                    return value
                if isinstance(value, dict):
                    keyed = value.get(key)
                    if isinstance(keyed, str):
                        return keyed
        env_value = os.environ.get(self._env_key(path, key))
        if env_value is not None:
            return env_value
        raise CredentialUnavailableError(key)

    def _put_sync(self, path: str, values: dict[str, str]) -> None:
        candidates = self._candidate_paths()
        target = candidates[0]
        target.parent.mkdir(parents=True, exist_ok=True)
        content: dict[str, Any] = {}
        if target.exists():
            loaded = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                content = loaded
        content[path] = values.get("value") if set(values) == {"value"} else dict(values)
        target.write_text(json.dumps(content, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    def _has_readable_file(self) -> bool:
        for candidate in self._candidate_paths():
            if not candidate.exists():
                continue
            try:
                json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                return False
            return True
        return False

    def _candidate_paths(self) -> list[Path]:
        configured = Path(self.secrets_file)
        candidates = [configured]
        if not configured.is_absolute():
            candidates.insert(0, Path.cwd() / configured)
        return candidates

    @staticmethod
    def _env_key(path: str, key: str) -> str:
        return "CONNECTOR_SECRET_" + "".join(
            char if char.isalnum() else "_" for char in f"{key}_{path}"
        ).upper()


class VaultSecretProvider:
    def __init__(self, settings: Any) -> None:
        if hvac is None:
            raise RuntimeError("hvac is required for VaultSecretProvider")
        self.settings = settings
        self._client = hvac.Client(
            url=getattr(settings, "addr", ""),
            namespace=getattr(settings, "namespace", "") or None,
            verify=True,
            timeout=getattr(settings, "retry_timeout_seconds", 10),
        )
        self._cache_ttl_seconds = int(getattr(settings, "cache_ttl_seconds", 60))
        self._cache_max_staleness_seconds = int(
            getattr(settings, "cache_max_staleness_seconds", 300)
        )
        self._cache: OrderedDict[str, tuple[datetime, str]] = OrderedDict()
        self._stale_cache: dict[str, tuple[datetime, str]] = {}
        self._last_successful_read: dict[str, datetime] = {}
        self._recent_failures: deque[str] = deque(maxlen=10)
        self._cache_hits = 0
        self._cache_misses = 0
        self._token_expiry_at: datetime | None = None
        self._lease_count: int | None = None
        self._renewal_task: asyncio.Task[None] | None = None
        self._authenticated = False
        self._clock_skew_seconds = 0.0
        self._sigterm_registered = False
        self._register_sigterm_handler()

    async def get(self, path: str, key: str = "value", *, critical: bool = False) -> str:
        validate_secret_path(path)
        cache_key = f"{path}#{key}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            self._record_cache_hit()
            return cached
        self._record_cache_miss()
        try:
            value = await self._read_secret(path, key=key)
        except CredentialPolicyDeniedError:
            VAULT_POLICY_DENIED_TOTAL.labels(path=path).inc()
            raise
        except Exception as exc:
            self._record_failure(exc)
            if not critical:
                stale = self._stale_value(cache_key)
                if stale is not None:
                    VAULT_SERVING_STALE_TOTAL.inc()
                    self._emit_event(
                        "vault.serving_stale",
                        path=path,
                        stale_age_seconds=self._stale_age_seconds(cache_key),
                    )
                    return stale
            self._emit_event("vault.unreachable", path=path, error=str(exc))
            raise CredentialUnavailableError(key) from exc
        self._cache_set(cache_key, value)
        self._last_successful_read[cache_key] = _now()
        self._stale_cache[cache_key] = (_now(), value)
        VAULT_READ_TOTAL.labels(domain=_domain_from_path(path)).inc()
        return value

    async def get_version(self, path: str, version: int, key: str = "value") -> str:
        validate_secret_path(path)
        return await self._read_secret(path, key=key, version=version)

    async def put(self, path: str, values: dict[str, str]) -> None:
        validate_secret_path(path)
        await self._ensure_authenticated()
        mount_point, secret_path = self._split_kv_path(path)
        last_error: Exception | None = None
        for _attempt in range(max(1, int(getattr(self.settings, "retry_attempts", 3)))):
            try:
                current_version = await self._latest_version(path)
                kwargs: dict[str, Any] = {
                    "path": secret_path,
                    "secret": values,
                    "mount_point": mount_point,
                }
                if current_version is not None:
                    kwargs["cas"] = current_version
                await asyncio.to_thread(
                    self._client.secrets.kv.v2.create_or_update_secret,
                    **kwargs,
                )
                self.flush_cache_sync(path)
                VAULT_WRITE_TOTAL.labels(domain=_domain_from_path(path)).inc()
                return
            except Exception as exc:  # hvac raises InvalidRequest on CAS conflicts
                last_error = exc
                await asyncio.sleep(0)
        raise CredentialUnavailableError(path) from last_error

    async def flush_cache(self, path: str | None = None) -> int:
        return self.flush_cache_sync(path)

    def flush_cache_sync(self, path: str | None = None) -> int:
        if path is None:
            count = len(self._cache) + len(self._stale_cache)
            self._cache.clear()
            self._stale_cache.clear()
            self._last_successful_read.clear()
            self._emit_event("vault.cache_flushed", path=None, flushed_count=count)
            return count
        prefix = f"{path}#"
        keys = [key for key in set(self._cache) | set(self._stale_cache) if key.startswith(prefix)]
        for key in keys:
            self._cache.pop(key, None)
            self._stale_cache.pop(key, None)
            self._last_successful_read.pop(key, None)
        self._emit_event("vault.cache_flushed", path=path, flushed_count=len(keys))
        return len(keys)

    async def delete_version(self, path: str, version: int) -> None:
        validate_secret_path(path)
        await self._ensure_authenticated()
        mount_point, secret_path = self._split_kv_path(path)
        await asyncio.to_thread(
            self._client.secrets.kv.v2.destroy_secret_versions,
            path=secret_path,
            versions=[version],
            mount_point=mount_point,
        )
        self.flush_cache_sync(path)

    async def list_versions(self, path: str) -> list[int]:
        validate_secret_path(path)
        metadata = await self._read_metadata(path)
        versions = metadata.get("versions") or {}
        return sorted(int(version) for version in versions)

    async def health_check(self) -> HealthStatus:
        try:
            await self._ensure_authenticated()
            health = await asyncio.to_thread(self._client.sys.read_health_status, method="GET")
            sealed = bool(health.get("sealed")) if isinstance(health, dict) else False
            lease_count = await self._read_lease_count()
            self._lease_count = lease_count
            if lease_count is not None:
                VAULT_LEASE_COUNT.labels(pod=os.getenv("HOSTNAME", "unknown")).set(lease_count)
            self._set_token_expiry_metric()
            return HealthStatus(
                status="red" if sealed else "green",
                auth_method=getattr(self.settings, "auth_method", None),
                token_expiry_at=self._token_expiry_at,
                lease_count=lease_count,
                recent_failures=list(self._recent_failures),
                cache_hit_rate=self._cache_hit_rate(),
                error="Vault is sealed" if sealed else None,
            )
        except Exception as exc:
            self._record_failure(exc)
            return HealthStatus(
                status="red",
                auth_method=getattr(self.settings, "auth_method", None),
                token_expiry_at=self._token_expiry_at,
                lease_count=self._lease_count,
                recent_failures=list(self._recent_failures),
                cache_hit_rate=self._cache_hit_rate(),
                error=str(exc),
            )

    async def _read_secret(self, path: str, *, key: str, version: int | None = None) -> str:
        await self._ensure_authenticated()
        mount_point, secret_path = self._split_kv_path(path)
        try:
            response = await asyncio.to_thread(
                self._client.secrets.kv.v2.read_secret_version,
                path=secret_path,
                version=version,
                mount_point=mount_point,
            )
        except Exception as exc:
            self._translate_vault_error(exc, key)
        data = response.get("data", {}).get("data", {}) if isinstance(response, dict) else {}
        self._detect_clock_skew(response)
        value = data.get(key)
        if not isinstance(value, str):
            raise CredentialUnavailableError(key)
        return value

    async def _read_metadata(self, path: str) -> dict[str, Any]:
        await self._ensure_authenticated()
        mount_point, secret_path = self._split_kv_path(path)
        try:
            response = await asyncio.to_thread(
                self._client.secrets.kv.v2.read_secret_metadata,
                path=secret_path,
                mount_point=mount_point,
            )
        except Exception as exc:
            self._translate_vault_error(exc, path)
        return response.get("data", {}) if isinstance(response, dict) else {}

    async def _latest_version(self, path: str) -> int | None:
        with contextlib.suppress(Exception):
            metadata = await self._read_metadata(path)
            current = metadata.get("current_version")
            return int(current) if current is not None else None
        return None

    def _translate_vault_error(self, exc: Exception, key: str) -> None:
        if hvac_exceptions is not None and isinstance(exc, hvac_exceptions.Forbidden):
            raise CredentialPolicyDeniedError(key) from exc
        if hvac_exceptions is not None and isinstance(exc, hvac_exceptions.InvalidPath):
            raise CredentialUnavailableError(key) from exc
        raise exc

    async def _ensure_authenticated(self) -> None:
        if self._authenticated and self._token_expiry_at and self._token_expiry_at > _now():
            return
        method = str(getattr(self.settings, "auth_method", "kubernetes"))
        try:
            if method == "kubernetes":
                await self._authenticate_kubernetes()
            elif method == "approle":
                await self._authenticate_approle()
            elif method == "token":
                await self._authenticate_token()
            else:
                raise CredentialUnavailableError(method)
        except Exception as exc:
            VAULT_AUTH_FAILURE_TOTAL.labels(auth_method=method).inc()
            self._record_failure(exc)
            raise
        self._authenticated = True
        self._start_renewal_loop()

    async def _authenticate_kubernetes(self) -> None:
        token_path = Path(getattr(self.settings, "service_account_token_path", ""))
        jwt = await asyncio.to_thread(token_path.read_text, encoding="utf-8")
        response = await asyncio.to_thread(
            self._client.auth.kubernetes.login,
            role=getattr(self.settings, "kubernetes_role", "musematic-platform"),
            jwt=jwt.strip(),
        )
        self._apply_auth_response(response)

    async def _authenticate_approle(self) -> None:
        secret_id_ref = getattr(self.settings, "approle_secret_id_secret_ref", "") or ""
        secret_id = await asyncio.to_thread(Path(secret_id_ref).read_text, encoding="utf-8")
        response = await asyncio.to_thread(
            self._client.auth.approle.login,
            role_id=getattr(self.settings, "approle_role_id", ""),
            secret_id=secret_id.strip(),
        )
        self._apply_auth_response(response)

    async def _authenticate_token(self) -> None:
        token = getattr(self.settings, "token", "")
        if not token:
            raise CredentialUnavailableError("vault-token")
        self._client.token = token
        lease_duration = 3600
        with contextlib.suppress(Exception):
            response = await asyncio.to_thread(self._client.auth.token.lookup_self)
            lease_duration = int(response.get("data", {}).get("ttl") or lease_duration)
        self._token_expiry_at = _now() + timedelta(seconds=lease_duration)
        self._set_token_expiry_metric()

    def _apply_auth_response(self, response: dict[str, Any]) -> None:
        auth = response.get("auth", {}) if isinstance(response, dict) else {}
        token = auth.get("client_token")
        if not isinstance(token, str) or not token:
            raise CredentialUnavailableError("vault-token")
        self._client.token = token
        lease_duration = int(auth.get("lease_duration") or 3600)
        self._token_expiry_at = _now() + timedelta(seconds=lease_duration)
        self._set_token_expiry_metric()
        self._emit_event(
            "vault.authenticated",
            auth_method=getattr(self.settings, "auth_method", None),
            token_expiry_at=self._token_expiry_at.isoformat(),
        )

    def _start_renewal_loop(self) -> None:
        if self._renewal_task is not None and not self._renewal_task.done():
            return
        with contextlib.suppress(RuntimeError):
            self._renewal_task = asyncio.create_task(self._renewal_loop())

    async def _renewal_loop(self) -> None:
        failures = 0
        while True:
            if self._token_expiry_at is None:
                return
            threshold = float(getattr(self.settings, "lease_renewal_threshold", 0.5))
            if abs(self._clock_skew_seconds) > 30:
                threshold = min(threshold, 0.4)
            seconds = max(1.0, (self._token_expiry_at - _now()).total_seconds() * threshold)
            await asyncio.sleep(seconds)
            try:
                response = await asyncio.to_thread(self._client.auth.token.renew_self)
                auth = response.get("auth", {}) if isinstance(response, dict) else {}
                ttl = int(auth.get("lease_duration") or auth.get("ttl") or 3600)
                self._token_expiry_at = _now() + timedelta(seconds=ttl)
                self._set_token_expiry_metric()
                VAULT_RENEWAL_SUCCESS_TOTAL.inc()
                self._emit_event(
                    "vault.lease_renewed",
                    token_expiry_at=self._token_expiry_at.isoformat(),
                )
                failures = 0
            except Exception as exc:
                failures += 1
                VAULT_RENEWAL_FAILURE_TOTAL.inc()
                self._record_failure(exc)
                if failures >= 3:
                    self._authenticated = False
                    await self._ensure_authenticated()
                    return

    def _register_sigterm_handler(self) -> None:
        if self._sigterm_registered:
            return
        with contextlib.suppress(ValueError):
            signal.signal(signal.SIGTERM, self._on_sigterm)
            self._sigterm_registered = True

    def _on_sigterm(self, _signum: int, _frame: Any) -> None:
        with contextlib.suppress(Exception):
            self._client.auth.token.revoke_self()
            self._emit_event("vault.lease_revoked")

    async def _read_lease_count(self) -> int | None:
        try:
            response = await asyncio.to_thread(self._client.sys.list_leases, prefix="")
            data = response.get("data", {}) if isinstance(response, dict) else {}
            keys = data.get("keys", [])
            return len(keys) if isinstance(keys, list) else None
        except Exception:
            return None

    def _split_kv_path(self, path: str) -> tuple[str, str]:
        mount = str(getattr(self.settings, "kv_mount", "secret") or "secret").strip("/")
        prefix = f"{mount}/data/"
        if not path.startswith(prefix):
            raise InvalidVaultPathError(path)
        return mount, path.removeprefix(prefix)

    def _cache_get(self, key: str) -> str | None:
        item = self._cache.get(key)
        if item is None:
            return None
        stored_at, value = item
        if (_now() - stored_at).total_seconds() > self._cache_ttl_seconds:
            self._cache.pop(key, None)
            return None
        self._cache.move_to_end(key)
        return value

    def _cache_set(self, key: str, value: str) -> None:
        self._cache[key] = (_now(), value)
        self._cache.move_to_end(key)
        while len(self._cache) > 1000:
            self._cache.popitem(last=False)

    def _stale_value(self, key: str) -> str | None:
        item = self._stale_cache.get(key)
        if item is None:
            return None
        stored_at, value = item
        if (_now() - stored_at).total_seconds() <= self._cache_max_staleness_seconds:
            return value
        return None

    def _stale_age_seconds(self, key: str) -> int:
        item = self._stale_cache.get(key)
        if item is None:
            return 0
        stored_at, _value = item
        return int((_now() - stored_at).total_seconds())

    def _record_cache_hit(self) -> None:
        self._cache_hits += 1
        VAULT_CACHE_HIT_TOTAL.inc()
        VAULT_CACHE_HIT_RATIO.set(self._cache_hit_rate())

    def _record_cache_miss(self) -> None:
        self._cache_misses += 1
        VAULT_CACHE_MISS_TOTAL.inc()
        VAULT_CACHE_HIT_RATIO.set(self._cache_hit_rate())

    def _cache_hit_rate(self) -> float:
        total = self._cache_hits + self._cache_misses
        return self._cache_hits / total if total else 0.0

    def _record_failure(self, exc: Exception) -> None:
        self._recent_failures.append(f"{type(exc).__name__}: {exc}")

    def _set_token_expiry_metric(self) -> None:
        if self._token_expiry_at is None:
            return
        seconds = max(0.0, (self._token_expiry_at - _now()).total_seconds())
        VAULT_TOKEN_EXPIRY_SECONDS.set(seconds)

    def _detect_clock_skew(self, response: Any) -> None:
        headers = response.get("headers", {}) if isinstance(response, dict) else {}
        raw_date = headers.get("Date") if isinstance(headers, dict) else None
        if not isinstance(raw_date, str):
            return
        with contextlib.suppress(Exception):
            server_time = parsedate_to_datetime(raw_date)
            if server_time.tzinfo is None:
                server_time = server_time.replace(tzinfo=UTC)
            skew = (server_time.astimezone(UTC) - _now()).total_seconds()
            self._clock_skew_seconds = skew
            if abs(skew) > 30:
                self._emit_event("vault.clock_skew_detected", skew_seconds=round(skew, 3))

    def _emit_event(self, event: str, **fields: Any) -> None:
        event_dict = vault_log_processor(None, "info", fields)
        with contextlib.suppress(Exception):
            import structlog

            structlog.get_logger(__name__).info(event, **event_dict)


class KubernetesSecretProvider:
    def __init__(
        self,
        settings: Any,
        *,
        namespace: str | None = None,
        api: Any | None = None,
    ) -> None:
        self.settings = settings
        self.namespace = namespace or os.getenv("PLATFORM_KUBERNETES_NAMESPACE", "platform")
        self._api = api

    async def get(self, path: str, key: str = "value", *, critical: bool = False) -> str:
        del critical
        validate_secret_path(path)
        api = await self._get_api()
        secret = await api.read_namespaced_secret(
            name=vault_path_to_k8s_secret_name(path),
            namespace=self.namespace,
        )
        data = getattr(secret, "data", {}) or {}
        raw = data.get(key)
        if raw is None:
            raise CredentialUnavailableError(key)
        return base64.b64decode(raw).decode("utf-8")

    async def put(self, path: str, values: dict[str, str]) -> None:
        validate_secret_path(path)
        api = await self._get_api()
        body = self._secret_body(path, values)
        name = vault_path_to_k8s_secret_name(path)
        try:
            await api.patch_namespaced_secret(name=name, namespace=self.namespace, body=body)
        except Exception:
            await api.create_namespaced_secret(namespace=self.namespace, body=body)

    async def flush_cache(self, path: str | None = None) -> int:
        del path
        return 0

    async def delete_version(self, path: str, version: int) -> None:
        del version
        validate_secret_path(path)

    async def list_versions(self, path: str) -> list[int]:
        validate_secret_path(path)
        return [1]

    async def health_check(self) -> HealthStatus:
        try:
            api = await self._get_api()
            await api.list_namespaced_secret(namespace=self.namespace, limit=1)
            return HealthStatus(status="green", auth_method="kubernetes")
        except Exception as exc:
            return HealthStatus(status="red", auth_method="kubernetes", error=str(exc))

    async def _get_api(self) -> Any:
        if self._api is not None:
            return self._api
        try:
            from kubernetes_asyncio import client, config
        except Exception as exc:
            raise RuntimeError(
                "kubernetes-asyncio is required for KubernetesSecretProvider"
            ) from exc
        with contextlib.suppress(Exception):
            config.load_incluster_config()  # type: ignore[no-untyped-call]
            self._api = client.CoreV1Api()
            return self._api
        await config.load_kube_config()
        self._api = client.CoreV1Api()
        return self._api

    def _secret_body(self, path: str, values: dict[str, str]) -> Any:
        try:
            from kubernetes_asyncio import client
        except Exception as exc:
            raise RuntimeError(
                "kubernetes-asyncio is required for KubernetesSecretProvider"
            ) from exc
        data = {
            key: base64.b64encode(value.encode("utf-8")).decode("ascii")
            for key, value in values.items()
        }
        return client.V1Secret(
            metadata=client.V1ObjectMeta(name=vault_path_to_k8s_secret_name(path)),
            type="Opaque",
            data=data,
        )
