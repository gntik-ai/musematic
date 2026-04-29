from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from platform.audit.repository import AuditChainRepository
from platform.audit.service import AuditChainService
from platform.auth.mfa import create_provisioning_uri, encrypt_secret, generate_totp_secret
from platform.auth.password import hash_password
from platform.auth.schemas import RoleType
from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from platform.common.logging import get_logger
from typing import Literal, NamedTuple
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

LOGGER = get_logger(__name__)

BOOTSTRAP_AUDIT_EVENT = "platform.superadmin.bootstrapped"
FORCE_RESET_AUDIT_EVENT = "platform.superadmin.force_reset"
BREAK_GLASS_AUDIT_EVENT = "platform.superadmin.break_glass_recovery"
ADMIN_AUDIT_SOURCE = "platform.admin"
BOOTSTRAP_SECRET_NAME = "platform-superadmin-bootstrap"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_BOOTSTRAP_LOCK_ID = 860_004


class BootstrapConfigError(RuntimeError):
    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class BootstrapConfig:
    username: str
    email: str
    password_file: Path | None
    env_password_present: bool
    mfa_enrollment: str
    force_password_change: bool
    instance_name: str
    tenant_mode: Literal["single", "multi"]
    force_reset: bool
    allow_reset: bool
    platform_env: str
    method: Literal["env_var", "cli"]
    recovery: bool


@dataclass(frozen=True)
class BootstrapResult:
    status: str
    user_id: UUID | None = None
    generated_credential: bool = False


class KubernetesServiceAccount(NamedTuple):
    host: str
    port: str
    token: str
    namespace: str
    ca_path: Path | None


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_env(
    *,
    method: Literal["env_var", "cli"],
    recovery: bool,
    environ: dict[str, str] | None = None,
) -> BootstrapConfig | None:
    source = environ if environ is not None else os.environ
    username = source.get("PLATFORM_SUPERADMIN_USERNAME", "").strip()
    if not username:
        return None

    email = source.get("PLATFORM_SUPERADMIN_EMAIL", "").strip().lower()
    if not email:
        raise BootstrapConfigError("PLATFORM_SUPERADMIN_EMAIL is required when username is set")
    if not _EMAIL_RE.fullmatch(email):
        raise BootstrapConfigError("PLATFORM_SUPERADMIN_EMAIL must be a valid email address")

    password_file_raw = source.get("PLATFORM_SUPERADMIN_PASSWORD_FILE", "").strip()
    env_value = source.get("PLATFORM_SUPERADMIN_PASSWORD")
    if password_file_raw and env_value:
        raise BootstrapConfigError(
            "Cannot set both PLATFORM_SUPERADMIN_PASSWORD and PLATFORM_SUPERADMIN_PASSWORD_FILE"
        )

    tenant_mode = source.get("PLATFORM_TENANT_MODE", "single").strip().lower()
    if tenant_mode not in {"single", "multi"}:
        raise BootstrapConfigError("PLATFORM_TENANT_MODE must be one of: single, multi")

    platform_env = source.get("PLATFORM_ENV", source.get("ENVIRONMENT", "production")).lower()
    force_reset = _truthy(source.get("PLATFORM_FORCE_RESET_SUPERADMIN"))
    allow_reset = _truthy(source.get("ALLOW_SUPERADMIN_RESET"))
    if force_reset and platform_env == "production" and not allow_reset:
        raise BootstrapConfigError(
            "PLATFORM_FORCE_RESET_SUPERADMIN requires ALLOW_SUPERADMIN_RESET=true in production",
            exit_code=2,
        )

    return BootstrapConfig(
        username=username,
        email=email,
        password_file=Path(password_file_raw) if password_file_raw else None,
        env_password_present=env_value is not None,
        mfa_enrollment=source.get(
            "PLATFORM_SUPERADMIN_MFA_ENROLLMENT",
            "required_on_first_login",
        ).strip(),
        force_password_change=_truthy(
            source.get("PLATFORM_SUPERADMIN_FORCE_PASSWORD_CHANGE", "true")
        ),
        instance_name=source.get("PLATFORM_INSTANCE_NAME", "Musematic Platform").strip()
        or "Musematic Platform",
        tenant_mode=tenant_mode,  # type: ignore[arg-type]
        force_reset=force_reset,
        allow_reset=allow_reset,
        platform_env=platform_env,
        method=method,
        recovery=recovery,
    )


async def bootstrap_superadmin_from_env(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    settings: PlatformSettings | None = None,
    method: Literal["env_var", "cli"] = "env_var",
    recovery: bool | None = None,
) -> BootstrapResult:
    config = _parse_env(method=method, recovery=bool(recovery))
    if config is None:
        return BootstrapResult(status="skipped_no_env")

    resolved_settings = settings or default_settings
    resolved_factory = session_factory or database.AsyncSessionLocal
    plain_value, generated = await _resolve_plaintext(config)
    try:
        credential_hash = _hash_and_zero(plain_value)
    finally:
        plain_value = "\0" * len(plain_value)

    async with resolved_factory() as session:
        async with session.begin():
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": _BOOTSTRAP_LOCK_ID},
            )
            user_id = await _find_superadmin_user(session, config)
            if config.force_reset:
                if user_id is None:
                    raise BootstrapConfigError(
                        "force reset requested but the target super admin does not exist",
                        exit_code=2,
                    )
                await _upsert_credential(session, user_id, config.email, credential_hash)
                await _append_admin_audit(
                    session,
                    resolved_settings,
                    event_type=FORCE_RESET_AUDIT_EVENT,
                    user_id=user_id,
                    config=config,
                    severity="critical",
                    extra={"reset": True},
                )
                await _notify_superadmins(
                    session,
                    exclude_user_id=user_id,
                    alert_type="superadmin_force_reset",
                    title="Super admin credential reset",
                    body=f"Super admin {config.username} was reset through the bootstrap path.",
                )
                return BootstrapResult(
                    status="force_reset",
                    user_id=user_id,
                    generated_credential=generated,
                )

            if user_id is not None:
                if await _bootstrap_audit_exists(session, config):
                    LOGGER.info(
                        "platform.superadmin.bootstrap.idempotent",
                        extra={
                            "username": config.username,
                            "email": config.email,
                        },
                    )
                    return BootstrapResult(
                        status="already_bootstrapped",
                        user_id=user_id,
                        generated_credential=generated,
                    )
                await _append_admin_audit(
                    session,
                    resolved_settings,
                    event_type=BOOTSTRAP_AUDIT_EVENT,
                    user_id=user_id,
                    config=config,
                    severity="info",
                    extra={"audit_recovered": True},
                )
                return BootstrapResult(
                    status="audit_recovered",
                    user_id=user_id,
                    generated_credential=generated,
                )

            user_id = await _create_superadmin(session, config, credential_hash, resolved_settings)
            await _append_admin_audit(
                session,
                resolved_settings,
                event_type=BREAK_GLASS_AUDIT_EVENT if config.recovery else BOOTSTRAP_AUDIT_EVENT,
                user_id=user_id,
                config=config,
                severity="critical" if config.recovery else "info",
                extra={"recovery": config.recovery},
            )
            if config.recovery:
                await _notify_superadmins(
                    session,
                    exclude_user_id=user_id,
                    alert_type="superadmin_break_glass_recovery",
                    title="Break-glass recovery used",
                    body=f"Break-glass recovery created super admin {config.username}.",
                )
            return BootstrapResult(
                status="created",
                user_id=user_id,
                generated_credential=generated,
            )


async def _resolve_plaintext(config: BootstrapConfig) -> tuple[str, bool]:
    if config.password_file is not None:
        try:
            return config.password_file.read_text(encoding="utf-8").strip(), False
        except OSError as exc:
            raise BootstrapConfigError(
                f"unable to read PLATFORM_SUPERADMIN_PASSWORD_FILE: {exc}"
            ) from exc

    env_value = os.environ.get("PLATFORM_SUPERADMIN_PASSWORD")
    if env_value is not None:
        return env_value, False

    generated = secrets.token_urlsafe(32)
    print(
        f"Generated super admin credential: {generated}\n"
        "save this — it will not be shown again",
        flush=True,
    )
    await _write_generated_credential_secret(generated)
    return generated, True


def _hash_and_zero(plain_value: str) -> str:
    mutable = bytearray(plain_value.encode("utf-8"))
    try:
        return hash_password(mutable.decode("utf-8"))
    finally:
        for index in range(len(mutable)):
            mutable[index] = 0


async def _write_generated_credential_secret(plain_value: str) -> None:
    account = _load_kubernetes_service_account()
    if account is None:
        return

    url = (
        f"https://{account.host}:{account.port}/api/v1/namespaces/"
        f"{account.namespace}/secrets"
    )
    body = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": BOOTSTRAP_SECRET_NAME,
            "annotations": {
                "kubernetes.io/auto-delete-after-retrieval": "true",
                "musematic.ai/one-time-retrieval": "true",
            },
        },
        "type": "Opaque",
        "data": {
            "password": base64.b64encode(plain_value.encode("utf-8")).decode("ascii"),
        },
    }
    verify: str | bool = str(account.ca_path) if account.ca_path is not None else True
    async with httpx.AsyncClient(verify=verify, timeout=5.0) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {account.token}"},
            json=body,
        )
        if response.status_code == 409:
            patch_url = f"{url}/{BOOTSTRAP_SECRET_NAME}"
            response = await client.patch(
                patch_url,
                headers={
                    "Authorization": f"Bearer {account.token}",
                    "Content-Type": "application/merge-patch+json",
                },
                json={"data": body["data"], "metadata": body["metadata"]},
            )
        response.raise_for_status()


def _load_kubernetes_service_account() -> KubernetesServiceAccount | None:
    host = os.environ.get("KUBERNETES_SERVICE_HOST")
    port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
    token_path = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
    namespace_path = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")
    ca_path = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
    if not host or not token_path.exists() or not namespace_path.exists():
        return None
    return KubernetesServiceAccount(
        host=host,
        port=port,
        token=token_path.read_text(encoding="utf-8").strip(),
        namespace=namespace_path.read_text(encoding="utf-8").strip(),
        ca_path=ca_path if ca_path.exists() else None,
    )


async def _find_superadmin_user(session: AsyncSession, config: BootstrapConfig) -> UUID | None:
    result = await session.execute(
        text(
            """
            SELECT id
            FROM users
            WHERE deleted_at IS NULL
              AND (email = :email OR username = :username)
            ORDER BY created_at ASC
            LIMIT 1
            FOR UPDATE
            """
        ),
        {"email": config.email, "username": config.username},
    )
    value = result.scalar_one_or_none()
    return UUID(str(value)) if value is not None else None


async def _bootstrap_audit_exists(session: AsyncSession, config: BootstrapConfig) -> bool:
    result = await session.execute(
        text(
            """
            SELECT 1
            FROM audit_chain_entries ace
            LEFT JOIN audit_events ae ON ae.id = ace.audit_event_id
            WHERE (ace.event_type = :event_type OR ae.event_type = :event_type)
              AND (
                ace.canonical_payload ->> 'username' = :username
                OR ace.canonical_payload ->> 'email' = :email
                OR ae.details ->> 'username' = :username
                OR ae.details ->> 'email' = :email
              )
            LIMIT 1
            """
        ),
        {
            "event_type": BOOTSTRAP_AUDIT_EVENT,
            "username": config.username,
            "email": config.email,
        },
    )
    return result.first() is not None


async def _create_superadmin(
    session: AsyncSession,
    config: BootstrapConfig,
    credential_hash: str,
    settings: PlatformSettings,
) -> UUID:
    mfa_required_before_login = config.mfa_enrollment == "required_before_first_login"
    result = await session.execute(
        text(
            """
            INSERT INTO users (
                username,
                email,
                display_name,
                status,
                mfa_pending,
                mfa_required_before_login,
                force_password_change,
                first_install_checklist_state
            )
            VALUES (
                :username,
                :email,
                :display_name,
                'active',
                :mfa_pending,
                :mfa_required_before_login,
                :force_password_change,
                NULL
            )
            RETURNING id
            """
        ),
        {
            "username": config.username,
            "email": config.email,
            "display_name": config.username,
            "mfa_pending": mfa_required_before_login,
            "mfa_required_before_login": mfa_required_before_login,
            "force_password_change": config.force_password_change,
        },
    )
    user_id = UUID(str(result.scalar_one()))
    await _upsert_credential(session, user_id, config.email, credential_hash)
    await _ensure_superadmin_role(session, user_id)
    await _upsert_platform_setting(session, "instance_name", config.instance_name)
    await _upsert_platform_setting(session, "tenant_mode", config.tenant_mode)
    if mfa_required_before_login:
        await _create_pending_mfa_enrollment(session, user_id, config.email, settings)
    return user_id


async def _upsert_credential(
    session: AsyncSession,
    user_id: UUID,
    email: str,
    credential_hash: str,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO user_credentials (user_id, email, password_hash, is_active)
            VALUES (:user_id, :email, :credential_hash, true)
            ON CONFLICT (user_id)
            DO UPDATE SET
                email = EXCLUDED.email,
                password_hash = EXCLUDED.password_hash,
                is_active = true,
                updated_at = now(),
                deleted_at = NULL
            """
        ),
        {"user_id": user_id, "email": email, "credential_hash": credential_hash},
    )


async def _ensure_superadmin_role(session: AsyncSession, user_id: UUID) -> None:
    await session.execute(
        text(
            """
            INSERT INTO user_roles (user_id, role, workspace_id)
            SELECT :user_id, :role, NULL
            WHERE NOT EXISTS (
                SELECT 1 FROM user_roles
                WHERE user_id = :user_id AND role = :role AND workspace_id IS NULL
            )
            """
        ),
        {"user_id": user_id, "role": RoleType.SUPERADMIN.value},
    )


async def _upsert_platform_setting(session: AsyncSession, key: str, value: str) -> None:
    await session.execute(
        text(
            """
            INSERT INTO platform_settings (key, value, scope, scope_id)
            VALUES (:key, CAST(:value AS jsonb), 'global', NULL)
            ON CONFLICT (key, scope) WHERE scope_id IS NULL
            DO UPDATE SET value = EXCLUDED.value, updated_at = now()
            """
        ),
        {"key": key, "value": json.dumps(value)},
    )


async def _create_pending_mfa_enrollment(
    session: AsyncSession,
    user_id: UUID,
    email: str,
    settings: PlatformSettings,
) -> None:
    if not settings.auth.mfa_encryption_key:
        raise BootstrapConfigError(
            "AUTH_MFA_ENCRYPTION_KEY is required for required_before_first_login MFA enrollment"
        )
    secret = generate_totp_secret()
    provisioning_uri = create_provisioning_uri(secret, email)
    qr_code = _render_terminal_qr_code(provisioning_uri)
    qr_output = f"\nMFA QR code:\n{qr_code}" if qr_code else ""
    print(
        f"MFA manual-entry secret: {secret}\n"
        f"MFA provisioning URI: {provisioning_uri}"
        f"{qr_output}",
        flush=True,
    )
    encrypted_secret = encrypt_secret(secret, settings.auth.mfa_encryption_key)
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.auth.mfa_enrollment_ttl)
    await session.execute(
        text(
            """
            INSERT INTO mfa_enrollments (
                user_id,
                method,
                encrypted_secret,
                status,
                recovery_codes_hash,
                expires_at
            )
            VALUES (:user_id, 'totp', :encrypted_secret, 'pending', '[]'::jsonb, :expires_at)
            """
        ),
        {
            "user_id": user_id,
            "encrypted_secret": encrypted_secret,
            "expires_at": expires_at,
        },
    )


def _render_terminal_qr_code(payload: str) -> str | None:
    qrencode = shutil.which("qrencode")
    if qrencode is None:
        return None
    try:
        result = subprocess.run(
            [qrencode, "-t", "ANSIUTF8", payload],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


async def _append_admin_audit(
    session: AsyncSession,
    settings: PlatformSettings,
    *,
    event_type: str,
    user_id: UUID,
    config: BootstrapConfig,
    severity: str,
    extra: dict[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {
        "event_type": event_type,
        "username": config.username,
        "email": config.email,
        "method": config.method,
        "mfa_enrollment": config.mfa_enrollment,
        "force_password_change": config.force_password_change,
        "instance_name": config.instance_name,
        "tenant_mode": config.tenant_mode,
        "platform_env": config.platform_env,
        "user_id": str(user_id),
    }
    if extra:
        payload.update(extra)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    event_id = await _insert_audit_event(session, event_type, user_id, payload)
    service = AuditChainService(AuditChainRepository(session), settings)
    await service.append(
        event_id,
        ADMIN_AUDIT_SOURCE,
        encoded,
        event_type=event_type,
        actor_role=RoleType.SUPERADMIN.value,
        severity=severity,
        canonical_payload_json=payload,
    )


async def _insert_audit_event(
    session: AsyncSession,
    event_type: str,
    user_id: UUID,
    payload: dict[str, object],
) -> UUID:
    result = await session.execute(
        text(
            """
            INSERT INTO audit_events (
                event_type,
                actor_id,
                actor_type,
                workspace_id,
                resource_type,
                resource_id,
                action,
                details
            )
            VALUES (
                :event_type,
                :actor_id,
                'system',
                NULL,
                'superadmin',
                :resource_id,
                :action,
                CAST(:details AS jsonb)
            )
            RETURNING id
            """
        ),
        {
            "event_type": event_type,
            "actor_id": user_id,
            "resource_id": user_id,
            "action": event_type,
            "details": json.dumps(payload, sort_keys=True),
        },
    )
    return UUID(str(result.scalar_one()))


async def _notify_superadmins(
    session: AsyncSession,
    *,
    exclude_user_id: UUID,
    alert_type: str,
    title: str,
    body: str,
) -> None:
    result = await session.execute(
        text(
            """
            SELECT DISTINCT u.id
            FROM users u
            JOIN user_roles ur ON ur.user_id = u.id
            WHERE ur.role = :role
              AND u.id <> :exclude_user_id
              AND u.deleted_at IS NULL
            """
        ),
        {"role": RoleType.SUPERADMIN.value, "exclude_user_id": exclude_user_id},
    )
    for row in result:
        await session.execute(
            text(
                """
                INSERT INTO user_alerts (
                    user_id,
                    interaction_id,
                    source_reference,
                    alert_type,
                    title,
                    body,
                    urgency,
                    read
                )
                VALUES (
                    :user_id,
                    NULL,
                    CAST(:source_reference AS jsonb),
                    :alert_type,
                    :title,
                    :body,
                    'critical',
                    false
                )
                """
            ),
            {
                "user_id": row[0],
                "source_reference": json.dumps({"type": "admin_bootstrap"}),
                "alert_type": alert_type,
                "title": title,
                "body": body,
            },
        )


async def _run_cli() -> int:
    try:
        result = await bootstrap_superadmin_from_env(
            method="cli" if _truthy(os.environ.get("PLATFORM_SUPERADMIN_CLI_MODE")) else "env_var",
            recovery=_truthy(os.environ.get("PLATFORM_SUPERADMIN_RECOVERY")),
        )
    except BootstrapConfigError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    print(
        json.dumps(
            {"status": result.status, "user_id": str(result.user_id) if result.user_id else None}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run_cli()))
