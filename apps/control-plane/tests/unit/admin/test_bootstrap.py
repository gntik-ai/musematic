from __future__ import annotations

from pathlib import Path
from platform.admin import bootstrap
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError


class _Result:
    def __init__(
        self,
        *,
        scalar: object | None = None,
        first: object | None = None,
        rows: list[tuple[object, ...]] | None = None,
    ) -> None:
        self._scalar = scalar
        self._first = first
        self._rows = rows or []

    def scalar_one_or_none(self) -> object | None:
        return self._scalar

    def scalar_one(self) -> object:
        assert self._scalar is not None
        return self._scalar

    def first(self) -> object | None:
        return self._first

    def __iter__(self):
        return iter(self._rows)


class _AsyncBlock:
    def __init__(self, value: object | None = None) -> None:
        self.value = value

    async def __aenter__(self) -> object | None:
        return self.value

    async def __aexit__(self, *_exc: object) -> None:
        return None


class _Session:
    def __init__(self, *results: _Result) -> None:
        self.results = list(results)
        self.executed: list[tuple[object, dict[str, object] | None]] = []
        self.added: list[object] = []
        self.flushed = False
        self.refreshed: list[object] = []

    def begin(self) -> _AsyncBlock:
        return _AsyncBlock()

    async def execute(
        self,
        statement: object,
        params: dict[str, object] | None = None,
    ) -> _Result:
        self.executed.append((statement, params))
        return self.results.pop(0) if self.results else _Result()

    def add(self, row: object) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        self.flushed = True

    async def refresh(self, row: object) -> None:
        self.refreshed.append(row)


class _SessionFactory:
    def __init__(self, session: _Session) -> None:
        self.session = session

    def __call__(self) -> _AsyncBlock:
        return _AsyncBlock(self.session)


def _config(**overrides: object) -> bootstrap.BootstrapConfig:
    values = {
        "username": "root",
        "email": "root@example.com",
        "password_file": None,
        "env_password_present": True,
        "mfa_enrollment": "required_on_first_login",
        "force_password_change": True,
        "instance_name": "Musematic",
        "tenant_mode": "single",
        "force_reset": False,
        "allow_reset": False,
        "platform_env": "production",
        "method": "env_var",
        "recovery": False,
    }
    values.update(overrides)
    return bootstrap.BootstrapConfig(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("", False),
        ("false", False),
        (" yes ", True),
        ("ON", True),
        ("0", False),
    ],
)
def test_truthy_accepts_operator_friendly_values(value: str | None, expected: bool) -> None:
    assert bootstrap._truthy(value) is expected


def test_parse_env_returns_none_without_username() -> None:
    assert bootstrap._parse_env(method="env_var", recovery=False, environ={}) is None


def test_parse_env_normalizes_valid_configuration() -> None:
    config = bootstrap._parse_env(
        method="cli",
        recovery=True,
        environ={
            "PLATFORM_SUPERADMIN_USERNAME": " root ",
            "PLATFORM_SUPERADMIN_EMAIL": " ROOT@EXAMPLE.COM ",
            "PLATFORM_SUPERADMIN_PASSWORD_FILE": "/run/secret/password",
            "PLATFORM_SUPERADMIN_MFA_ENROLLMENT": "required_before_first_login",
            "PLATFORM_SUPERADMIN_FORCE_PASSWORD_CHANGE": "false",
            "PLATFORM_INSTANCE_NAME": " ",
            "PLATFORM_TENANT_MODE": "multi",
            "PLATFORM_FORCE_RESET_SUPERADMIN": "true",
            "ALLOW_SUPERADMIN_RESET": "true",
            "ENVIRONMENT": "production",
        },
    )

    assert config is not None
    assert config.username == "root"
    assert config.email == "root@example.com"
    assert config.password_file == Path("/run/secret/password")
    assert config.mfa_enrollment == "required_before_first_login"
    assert config.force_password_change is False
    assert config.instance_name == "Musematic Platform"
    assert config.tenant_mode == "multi"
    assert config.force_reset is True
    assert config.allow_reset is True
    assert config.method == "cli"
    assert config.recovery is True


@pytest.mark.parametrize(
    ("environ", "message", "exit_code"),
    [
        (
            {"PLATFORM_SUPERADMIN_USERNAME": "root"},
            "PLATFORM_SUPERADMIN_EMAIL is required",
            1,
        ),
        (
            {
                "PLATFORM_SUPERADMIN_USERNAME": "root",
                "PLATFORM_SUPERADMIN_EMAIL": "not-email",
            },
            "must be a valid email",
            1,
        ),
        (
            {
                "PLATFORM_SUPERADMIN_USERNAME": "root",
                "PLATFORM_SUPERADMIN_EMAIL": "root@example.com",
                "PLATFORM_SUPERADMIN_PASSWORD": "secret",
                "PLATFORM_SUPERADMIN_PASSWORD_FILE": "/run/secret/password",
            },
            "mutually exclusive",
            1,
        ),
        (
            {
                "PLATFORM_SUPERADMIN_USERNAME": "root",
                "PLATFORM_SUPERADMIN_EMAIL": "root@example.com",
                "PLATFORM_TENANT_MODE": "invalid",
            },
            "PLATFORM_TENANT_MODE",
            1,
        ),
        (
            {
                "PLATFORM_SUPERADMIN_USERNAME": "root",
                "PLATFORM_SUPERADMIN_EMAIL": "root@example.com",
                "PLATFORM_FORCE_RESET_SUPERADMIN": "true",
                "PLATFORM_ENV": "production",
            },
            "ALLOW_SUPERADMIN_RESET",
            2,
        ),
    ],
)
def test_parse_env_rejects_invalid_configuration(
    environ: dict[str, str],
    message: str,
    exit_code: int,
) -> None:
    with pytest.raises(bootstrap.BootstrapConfigError, match=message) as exc_info:
        bootstrap._parse_env(method="env_var", recovery=False, environ=environ)

    assert exc_info.value.exit_code == exit_code


@pytest.mark.asyncio
async def test_resolve_plaintext_reads_password_file(tmp_path: Path) -> None:
    password_file = tmp_path / "password"
    password_file.write_text("  secret\n", encoding="utf-8")

    assert await bootstrap._resolve_plaintext(_config(password_file=password_file)) == (
        "secret",
        False,
    )


@pytest.mark.asyncio
async def test_resolve_plaintext_wraps_file_read_errors(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    with pytest.raises(bootstrap.BootstrapConfigError, match="unable to read"):
        await bootstrap._resolve_plaintext(_config(password_file=missing))


@pytest.mark.asyncio
async def test_resolve_plaintext_uses_env_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATFORM_SUPERADMIN_PASSWORD", "from-env")

    assert await bootstrap._resolve_plaintext(_config(env_password_present=True)) == (
        "from-env",
        False,
    )


@pytest.mark.asyncio
async def test_resolve_plaintext_generates_and_persists_once(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    generated: list[str] = []

    async def fake_write(value: str) -> None:
        generated.append(value)

    monkeypatch.delenv("PLATFORM_SUPERADMIN_PASSWORD", raising=False)
    monkeypatch.setattr(bootstrap.secrets, "token_urlsafe", lambda _size: "generated-secret")
    monkeypatch.setattr(bootstrap, "_write_generated_credential_secret", fake_write)

    assert await bootstrap._resolve_plaintext(_config(env_password_present=False)) == (
        "generated-secret",
        True,
    )
    assert generated == ["generated-secret"]
    assert "Generated super admin credential: generated-secret" in capsys.readouterr().out


def test_hash_and_zero_delegates_to_password_hasher(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap, "hash_password", lambda value: f"hashed:{value}")

    assert bootstrap._hash_and_zero("plain") == "hashed:plain"


@pytest.mark.asyncio
async def test_write_generated_credential_secret_returns_without_service_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap, "_load_kubernetes_service_account", lambda: None)

    await bootstrap._write_generated_credential_secret("secret")


@pytest.mark.asyncio
async def test_write_generated_credential_secret_creates_or_patches_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    class _Response:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

        def raise_for_status(self) -> None:
            calls.append(("raise", str(self.status_code), None))

    class _Client:
        def __init__(self, *, verify: str | bool, timeout: float) -> None:
            calls.append(("init", str(verify), {"timeout": timeout}))

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, object],
        ) -> _Response:
            calls.append(("post", url, {"headers": headers, "json": json}))
            return _Response(409)

        async def patch(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, object],
        ) -> _Response:
            calls.append(("patch", url, {"headers": headers, "json": json}))
            return _Response(200)

    monkeypatch.setattr(
        bootstrap,
        "_load_kubernetes_service_account",
        lambda: bootstrap.KubernetesServiceAccount(
            host="kubernetes.default",
            port="443",
            token="token",
            namespace="platform",
            ca_path=Path("/ca.crt"),
        ),
    )
    monkeypatch.setattr(bootstrap.httpx, "AsyncClient", _Client)

    await bootstrap._write_generated_credential_secret("secret")

    post_call = next(call for call in calls if call[0] == "post")
    patch_call = next(call for call in calls if call[0] == "patch")
    assert post_call[1].endswith("/api/v1/namespaces/platform/secrets")
    assert patch_call[1].endswith("/secrets/platform-superadmin-bootstrap")
    assert post_call[2] is not None
    assert post_call[2]["json"]["data"]["password"] == "c2VjcmV0"  # type: ignore[index]


def test_load_kubernetes_service_account_returns_none_without_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)

    assert bootstrap._load_kubernetes_service_account() is None


@pytest.mark.asyncio
async def test_find_superadmin_user_returns_uuid_or_none() -> None:
    user_id = uuid4()
    config = _config()

    assert await bootstrap._find_superadmin_user(_Session(_Result(scalar=user_id)), config) == user_id
    assert await bootstrap._find_superadmin_user(_Session(_Result()), config) is None


@pytest.mark.asyncio
async def test_bootstrap_audit_exists_checks_any_row() -> None:
    config = _config()

    assert await bootstrap._bootstrap_audit_exists(_Session(_Result(first=(1,))), config) is True
    assert await bootstrap._bootstrap_audit_exists(_Session(_Result()), config) is False


@pytest.mark.asyncio
async def test_write_helpers_emit_expected_database_parameters() -> None:
    user_id = uuid4()
    session = _Session()

    await bootstrap._upsert_credential(session, user_id, "root@example.com", "hash")
    await bootstrap._ensure_superadmin_role(session, user_id)
    await bootstrap._upsert_platform_setting(session, "instance_name", "Musematic")

    assert session.executed[0][1] == {
        "user_id": user_id,
        "email": "root@example.com",
        "credential_hash": "hash",
    }
    assert session.executed[1][1] == {"user_id": user_id, "role": "superadmin"}
    assert session.executed[2][1] == {"key": "instance_name", "value": '"Musematic"'}


@pytest.mark.asyncio
async def test_create_superadmin_writes_user_role_settings_and_mfa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    session = _Session(_Result(scalar=user_id))
    calls: list[tuple[str, object]] = []

    async def record(name: str, *args: object) -> None:
        calls.append((name, args))

    monkeypatch.setattr(bootstrap, "_upsert_credential", lambda *args: record("credential", *args))
    monkeypatch.setattr(
        bootstrap,
        "_ensure_superadmin_role",
        lambda *args: record("role", *args),
    )
    monkeypatch.setattr(
        bootstrap,
        "_upsert_platform_setting",
        lambda *args: record("setting", *args),
    )
    monkeypatch.setattr(
        bootstrap,
        "_create_pending_mfa_enrollment",
        lambda *args: record("mfa", *args),
    )

    created = await bootstrap._create_superadmin(
        session,
        _config(mfa_enrollment="required_before_first_login"),
        "hash",
        SimpleNamespace(auth=SimpleNamespace()),
    )

    assert created == user_id
    assert {name for name, _args in calls} == {"credential", "role", "setting", "mfa"}
    assert session.executed[0][1]["mfa_pending"] is True  # type: ignore[index]


@pytest.mark.asyncio
async def test_create_pending_mfa_enrollment_requires_encryption_key() -> None:
    with pytest.raises(bootstrap.BootstrapConfigError, match="AUTH_MFA_ENCRYPTION_KEY"):
        await bootstrap._create_pending_mfa_enrollment(
            _Session(),
            uuid4(),
            "root@example.com",
            SimpleNamespace(auth=SimpleNamespace(mfa_encryption_key=None)),
        )


@pytest.mark.asyncio
async def test_create_pending_mfa_enrollment_persists_encrypted_secret(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session = _Session()
    user_id = uuid4()
    monkeypatch.setattr(bootstrap, "generate_totp_secret", lambda: "totp-secret")
    monkeypatch.setattr(
        bootstrap,
        "create_provisioning_uri",
        lambda secret, email: f"otpauth://{email}/{secret}",
    )
    monkeypatch.setattr(bootstrap, "encrypt_secret", lambda secret, key: f"{key}:{secret}")

    await bootstrap._create_pending_mfa_enrollment(
        session,
        user_id,
        "root@example.com",
        SimpleNamespace(
            auth=SimpleNamespace(mfa_encryption_key="key", mfa_enrollment_ttl=600),
        ),
    )

    assert session.executed[0][1]["user_id"] == user_id  # type: ignore[index]
    assert session.executed[0][1]["encrypted_secret"] == "key:totp-secret"  # type: ignore[index]
    assert "MFA manual-entry secret: totp-secret" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_insert_audit_event_returns_event_id() -> None:
    event_id = uuid4()
    user_id = uuid4()

    assert (
        await bootstrap._insert_audit_event(
            _Session(_Result(scalar=event_id)),
            bootstrap.BOOTSTRAP_AUDIT_EVENT,
            user_id,
            {"ok": True},
        )
        == event_id
    )


@pytest.mark.asyncio
async def test_append_admin_audit_builds_canonical_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_id = uuid4()
    user_id = uuid4()
    appended: list[dict[str, object]] = []

    class _AuditService:
        def __init__(self, repository: object, settings: object) -> None:
            appended.append({"repository": repository, "settings": settings})

        async def append(self, *args: object, **kwargs: object) -> None:
            appended.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(bootstrap, "_insert_audit_event", lambda *args: _return(event_id))
    monkeypatch.setattr(bootstrap, "AuditChainRepository", lambda session: ("repo", session))
    monkeypatch.setattr(bootstrap, "AuditChainService", _AuditService)

    await bootstrap._append_admin_audit(
        _Session(),
        SimpleNamespace(),
        event_type=bootstrap.BOOTSTRAP_AUDIT_EVENT,
        user_id=user_id,
        config=_config(),
        severity="info",
        extra={"recovery": False},
    )

    append_call = appended[-1]
    kwargs = append_call["kwargs"]
    assert kwargs["actor_role"] == "superadmin"  # type: ignore[index]
    assert kwargs["canonical_payload_json"]["user_id"] == str(user_id)  # type: ignore[index]
    assert kwargs["canonical_payload_json"]["recovery"] is False  # type: ignore[index]


async def _return(value: object) -> object:
    return value


@pytest.mark.asyncio
async def test_notify_superadmins_inserts_alerts_for_other_admins() -> None:
    first = uuid4()
    second = uuid4()
    session = _Session(_Result(rows=[(first,), (second,)]))

    await bootstrap._notify_superadmins(
        session,
        exclude_user_id=uuid4(),
        alert_type="superadmin_force_reset",
        title="Reset",
        body="Credential reset",
    )

    assert len(session.executed) == 3
    assert session.executed[1][1]["user_id"] == first  # type: ignore[index]
    assert session.executed[2][1]["alert_type"] == "superadmin_force_reset"  # type: ignore[index]


@pytest.mark.parametrize(
    ("find_user", "audit_exists", "force_reset", "recovery", "expected_status"),
    [
        (uuid4(), None, True, False, "force_reset"),
        (uuid4(), True, False, False, "already_bootstrapped"),
        (uuid4(), False, False, False, "audit_recovered"),
        (None, None, False, True, "created"),
    ],
)
@pytest.mark.asyncio
async def test_bootstrap_superadmin_from_env_branches(
    monkeypatch: pytest.MonkeyPatch,
    find_user: UUID | None,
    audit_exists: bool | None,
    force_reset: bool,
    recovery: bool,
    expected_status: str,
) -> None:
    created_user = uuid4()
    calls: list[str] = []
    config = _config(force_reset=force_reset, recovery=recovery)

    monkeypatch.setattr(bootstrap, "_parse_env", lambda **_kwargs: config)
    monkeypatch.setattr(bootstrap, "_resolve_plaintext", lambda _config: _return(("plain", False)))
    monkeypatch.setattr(bootstrap, "_hash_and_zero", lambda _plain: "hash")
    monkeypatch.setattr(bootstrap, "_find_superadmin_user", lambda *_args: _return(find_user))
    monkeypatch.setattr(
        bootstrap,
        "_bootstrap_audit_exists",
        lambda *_args: _return(bool(audit_exists)),
    )
    monkeypatch.setattr(bootstrap, "_upsert_credential", lambda *_args: _record(calls, "upsert"))
    monkeypatch.setattr(bootstrap, "_append_admin_audit", lambda *_args, **_kwargs: _record(calls, "audit"))
    monkeypatch.setattr(bootstrap, "_notify_superadmins", lambda *_args, **_kwargs: _record(calls, "notify"))
    monkeypatch.setattr(bootstrap, "_create_superadmin", lambda *_args: _return(created_user))

    result = await bootstrap.bootstrap_superadmin_from_env(
        session_factory=_SessionFactory(_Session()),
        settings=SimpleNamespace(),
        recovery=recovery,
    )

    assert result.status == expected_status
    assert result.user_id == (created_user if find_user is None else find_user)
    if expected_status in {"force_reset", "created"}:
        assert "notify" in calls


async def _record(calls: list[str], value: str) -> None:
    calls.append(value)


@pytest.mark.asyncio
async def test_bootstrap_superadmin_from_env_handles_no_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap, "_parse_env", lambda **_kwargs: None)

    result = await bootstrap.bootstrap_superadmin_from_env()

    assert result.status == "skipped_no_env"


@pytest.mark.asyncio
async def test_bootstrap_superadmin_from_env_rejects_force_reset_without_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap, "_parse_env", lambda **_kwargs: _config(force_reset=True))
    monkeypatch.setattr(bootstrap, "_resolve_plaintext", lambda _config: _return(("plain", False)))
    monkeypatch.setattr(bootstrap, "_hash_and_zero", lambda _plain: "hash")
    monkeypatch.setattr(bootstrap, "_find_superadmin_user", lambda *_args: _return(None))

    with pytest.raises(bootstrap.BootstrapConfigError, match="does not exist") as exc_info:
        await bootstrap.bootstrap_superadmin_from_env(
            session_factory=_SessionFactory(_Session()),
            settings=SimpleNamespace(),
        )

    assert exc_info.value.exit_code == 2


@pytest.mark.asyncio
async def test_run_cli_reports_success_or_config_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    user_id = uuid4()
    monkeypatch.setenv("PLATFORM_SUPERADMIN_CLI_MODE", "true")
    monkeypatch.setenv("PLATFORM_SUPERADMIN_RECOVERY", "true")
    monkeypatch.setattr(
        bootstrap,
        "bootstrap_superadmin_from_env",
        lambda **_kwargs: _return(bootstrap.BootstrapResult("created", user_id)),
    )

    assert await bootstrap._run_cli() == 0
    assert f'"user_id": "{user_id}"' in capsys.readouterr().out

    async def fail(**_kwargs: object) -> bootstrap.BootstrapResult:
        raise bootstrap.BootstrapConfigError("bad config", exit_code=7)

    monkeypatch.setattr(bootstrap, "bootstrap_superadmin_from_env", fail)

    assert await bootstrap._run_cli() == 7
    assert "bad config" in capsys.readouterr().err


def test_bootstrap_config_error_stores_exit_code() -> None:
    error = bootstrap.BootstrapConfigError("bad", exit_code=9)

    assert str(error) == "bad"
    assert error.exit_code == 9
