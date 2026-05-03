"""DPA upload, versioning, and storage for Enterprise tenants.

Workflow (FR-756):
1. Validate magic bytes ``%PDF-`` and file size <= 50 MB.
2. Submit to ClamAV; reject on virus, fail-closed on scanner unreachable.
3. Compute SHA-256 of cleartext bytes.
4. Persist to Vault at the per-tenant DPA path; audit + Kafka.
5. Update ``tenants.dpa_*`` columns (hash, version, signed_at, vault path).

Versioning is append-only — every upload bumps ``dpa_version``. The
prior version remains addressable in Vault for audit until cascade
deletion (US3 phase_2 calls :func:`enumerate_dpa_paths_for_tenant`).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from platform.common.config import DataLifecycleSettings
from platform.data_lifecycle.exceptions import (
    DPAPdfInvalidError,
    DPAScanUnavailableError,
    DPATooLargeError,
    DPAVersionAlreadyExistsError,
    DPAVersionNotFoundError,
    DPAVirusDetectedError,
    VaultUnreachableError,
)
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MAX_DPA_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB
PDF_MAGIC: bytes = b"%PDF-"
VERSION_RE = re.compile(r"^v[0-9]+(\.[0-9]+){0,2}$")


@dataclass(frozen=True, slots=True)
class DPAUploadResult:
    tenant_id: UUID
    version: str
    effective_date: date
    sha256: str
    vault_path: str


class _ClamAVScanner(Protocol):
    """Subset of the ``clamd`` async client we use.

    The implementation calls ``clamd.scan(BytesIO)`` under
    ``asyncio.to_thread`` since ``clamd`` is a sync library.
    """

    async def scan_bytes(self, payload: bytes, *, timeout_seconds: float) -> str | None:
        """Return the matched signature name, or None if clean.

        Raises ``DPAScanUnavailableError`` if the daemon is unreachable.
        """


class _SecretStore(Protocol):
    async def put(self, path: str, values: dict[str, str]) -> None:
        ...

    async def get(self, path: str, key: str = "value", *, critical: bool = False) -> str:
        ...

    async def delete_version(self, path: str, version: int) -> None:
        ...


class _AuditAppender(Protocol):
    async def append(
        self, audit_event_id: UUID, namespace: str, canonical_payload: bytes
    ) -> Any:
        ...


class _EventProducer(Protocol):
    async def publish(self, **kwargs: Any) -> Any:
        ...


class DPAService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: DataLifecycleSettings,
        environment: str,
        secret_store: _SecretStore,
        clamav_scanner: _ClamAVScanner | None,
        audit_chain: _AuditAppender | None,
        event_producer: _EventProducer | None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._environment = environment
        self._vault = secret_store
        self._clamav = clamav_scanner
        self._audit = audit_chain
        self._producer = event_producer

    async def upload(
        self,
        *,
        tenant_id: UUID,
        version: str,
        effective_date: date,
        pdf_bytes: bytes,
        actor_user_id: UUID,
    ) -> DPAUploadResult:
        """Upload a new DPA version for a tenant."""

        # 1. Size + magic-bytes guard.
        if len(pdf_bytes) > MAX_DPA_SIZE_BYTES:
            raise DPATooLargeError(
                f"DPA exceeds {MAX_DPA_SIZE_BYTES // (1024 * 1024)} MB limit"
            )
        if not pdf_bytes.startswith(PDF_MAGIC):
            raise DPAPdfInvalidError("file does not start with %PDF- magic bytes")
        if not VERSION_RE.match(version):
            raise DPAPdfInvalidError(
                f"version must match {VERSION_RE.pattern!r}; got {version!r}"
            )

        # 2. Tenant + version-collision check.
        slug = await self._tenant_slug_or_raise(tenant_id)
        existing_version = await self._read_existing_version(tenant_id)
        if existing_version == version:
            raise DPAVersionAlreadyExistsError(
                f"tenant {tenant_id} already has DPA version {version}"
            )

        # 3. Virus scan (R3).
        signature = await self._scan_or_raise(pdf_bytes)
        if signature is not None:
            await self._emit_audit(
                event_type="data_lifecycle.dpa_rejected_virus",
                payload={
                    "tenant_id": str(tenant_id),
                    "version": version,
                    "signature": signature,
                    "actor_user_id": str(actor_user_id),
                    "rejected_at": _utcnow_iso(),
                },
            )
            raise DPAVirusDetectedError(f"DPA rejected: signature {signature}")

        # 4. Hash + Vault write.
        sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        vault_path = self._vault_path(slug=slug, version=version)
        try:
            await self._vault.put(
                vault_path,
                {
                    "value": base64.b64encode(pdf_bytes).decode("ascii"),
                    "sha256": sha256,
                    "version": version,
                    "effective_date": effective_date.isoformat(),
                    "uploaded_by_user_id": str(actor_user_id),
                    "uploaded_at": _utcnow_iso(),
                },
            )
        except Exception as exc:
            logger.exception("data_lifecycle.dpa_vault_write_failed")
            raise VaultUnreachableError(f"vault write failed: {exc}") from exc

        # 5. Tenant row update.
        await self._session.execute(
            text(
                """
                UPDATE tenants
                SET
                    dpa_signed_at = :signed_at,
                    dpa_version = :version,
                    dpa_artifact_uri = :uri,
                    dpa_artifact_sha256 = :sha256
                WHERE id = :tenant_id
                """
            ),
            {
                "signed_at": datetime.combine(effective_date, datetime.min.time(), UTC),
                "version": version,
                "uri": vault_path,
                "sha256": sha256,
                "tenant_id": str(tenant_id),
            },
        )

        # 6. Audit + Kafka.
        now = datetime.now(UTC)
        await self._emit_audit(
            event_type="data_lifecycle.dpa_uploaded",
            payload={
                "tenant_id": str(tenant_id),
                "version": version,
                "sha256": sha256,
                "effective_date": effective_date.isoformat(),
                "vault_path_redacted": self._redacted_path(slug=slug, version=version),
                "actor_user_id": str(actor_user_id),
                "uploaded_at": now.isoformat(),
            },
        )
        await self._publish_uploaded_event(
            tenant_id=tenant_id,
            version=version,
            sha256=sha256,
            effective_date=effective_date,
        )
        return DPAUploadResult(
            tenant_id=tenant_id,
            version=version,
            effective_date=effective_date,
            sha256=sha256,
            vault_path=vault_path,
        )

    async def get_active(self, tenant_id: UUID) -> dict[str, Any] | None:
        """Return the active DPA metadata (no PDF bytes)."""

        result = await self._session.execute(
            text(
                """
                SELECT
                    dpa_version, dpa_signed_at, dpa_artifact_sha256, dpa_artifact_uri
                FROM tenants WHERE id = :tenant_id
                """
            ),
            {"tenant_id": str(tenant_id)},
        )
        row = result.mappings().first()
        if row is None or row["dpa_version"] is None:
            return None
        return {
            "version": row["dpa_version"],
            "signed_at": (
                row["dpa_signed_at"].isoformat()
                if row["dpa_signed_at"]
                else None
            ),
            "sha256": row["dpa_artifact_sha256"],
            "vault_path": row["dpa_artifact_uri"],
        }

    async def download(
        self, *, tenant_id: UUID, version: str, actor_user_id: UUID
    ) -> bytes:
        slug = await self._tenant_slug_or_raise(tenant_id)
        vault_path = self._vault_path(slug=slug, version=version)
        try:
            encoded = await self._vault.get(vault_path, "value", critical=False)
            stored_hash = await self._vault.get(vault_path, "sha256", critical=False)
        except Exception as exc:
            # Distinguish 404 from connectivity if the underlying provider exposes it.
            msg = str(exc).lower()
            if "not found" in msg or "no value" in msg:
                raise DPAVersionNotFoundError(
                    f"DPA version {version} not found for tenant {tenant_id}"
                ) from exc
            raise VaultUnreachableError(f"vault read failed: {exc}") from exc

        try:
            pdf_bytes = base64.b64decode(encoded.encode("ascii"))
        except Exception as exc:
            raise VaultUnreachableError("vault payload corrupt") from exc

        # Defense-in-depth: verify content hash matches Vault metadata.
        computed = hashlib.sha256(pdf_bytes).hexdigest()
        if stored_hash and computed != stored_hash:
            raise VaultUnreachableError("hash mismatch on DPA download")

        await self._emit_audit(
            event_type="data_lifecycle.dpa_downloaded",
            payload={
                "tenant_id": str(tenant_id),
                "version": version,
                "actor_user_id": str(actor_user_id),
                "downloaded_at": _utcnow_iso(),
            },
        )
        return pdf_bytes

    def vault_path_for(self, *, slug: str, version: str) -> str:
        return self._vault_path(slug=slug, version=version)

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _vault_path(self, *, slug: str, version: str) -> str:
        return self._settings.dpa_vault_path_template.format(
            env=self._environment, slug=slug, version=version
        )

    def _redacted_path(self, *, slug: str, version: str) -> str:
        # Replace concrete environment with a literal "{env}" placeholder
        # so the audit + event payloads cannot be used to reconstruct the
        # exact path.
        return self._settings.dpa_vault_path_template.format(
            env="{env}", slug=slug, version=version
        )

    async def _tenant_slug_or_raise(self, tenant_id: UUID) -> str:
        result = await self._session.execute(
            text("SELECT slug FROM tenants WHERE id = :tenant_id"),
            {"tenant_id": str(tenant_id)},
        )
        row = result.mappings().first()
        if row is None:
            raise DPAVersionNotFoundError(f"tenant {tenant_id} not found")
        return str(row["slug"])

    async def _read_existing_version(self, tenant_id: UUID) -> str | None:
        result = await self._session.execute(
            text("SELECT dpa_version FROM tenants WHERE id = :tenant_id"),
            {"tenant_id": str(tenant_id)},
        )
        row = result.mappings().first()
        return None if row is None else row["dpa_version"]

    async def _scan_or_raise(self, pdf_bytes: bytes) -> str | None:
        """Return the matched signature name (positive) or None (clean).

        Raises :class:`DPAScanUnavailableError` if the scanner is unreachable.
        Bypasses scanning when ``self._clamav is None`` — the operator
        is expected to set the env var in dev/test only.
        """

        if self._clamav is None:
            logger.warning("data_lifecycle.dpa_scan_skipped_no_clamav")
            return None
        try:
            return await self._clamav.scan_bytes(
                pdf_bytes,
                timeout_seconds=self._settings.clamav_timeout_seconds,
            )
        except DPAScanUnavailableError:
            await self._emit_audit(
                event_type="data_lifecycle.dpa_scan_unavailable",
                payload={"checked_at": _utcnow_iso()},
            )
            raise

    async def _emit_audit(
        self, *, event_type: str, payload: dict[str, Any]
    ) -> None:
        if self._audit is None:
            return
        canonical = json.dumps(
            {"event_type": event_type, **payload},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            await self._audit.append(uuid4(), "data_lifecycle", canonical)
        except Exception:
            logger.exception("data_lifecycle.audit_emission_failed")

    async def _publish_uploaded_event(
        self,
        *,
        tenant_id: UUID,
        version: str,
        sha256: str,
        effective_date: date,
    ) -> None:
        if self._producer is None:
            return
        from platform.common.events.envelope import CorrelationContext
        from platform.data_lifecycle.events import (
            DataLifecycleEventType,
            DPAUploadedPayload,
            publish_data_lifecycle_event,
        )

        ctx = CorrelationContext(correlation_id=uuid4())
        payload = DPAUploadedPayload(
            tenant_id=tenant_id,
            dpa_version=version,
            sha256=sha256,
            effective_date=datetime.combine(effective_date, datetime.min.time(), UTC),
            vault_path_redacted=self._redacted_path(
                slug=await self._tenant_slug_or_raise(tenant_id),
                version=version,
            ),
            correlation_context=ctx,
        )
        await publish_data_lifecycle_event(
            self._producer,  # type: ignore[arg-type]  # type: ignore[arg-type]
            DataLifecycleEventType.dpa_uploaded,
            payload,
            ctx,
            partition_key=tenant_id,
        )


# =============================================================================
# ClamAV adapter
# =============================================================================


class ClamdScanAdapter:
    """Thin wrapper around the sync ``clamd`` Python client.

    Calls run in a worker thread via ``asyncio.to_thread`` so the
    request loop never blocks. The wrapper raises
    :class:`DPAScanUnavailableError` when the daemon is unreachable.
    """

    def __init__(self, *, host: str, port: int) -> None:
        self._host = host
        self._port = port

    async def scan_bytes(
        self, payload: bytes, *, timeout_seconds: float
    ) -> str | None:
        try:
            import clamd
        except ImportError as exc:
            raise DPAScanUnavailableError("clamd python client not installed") from exc

        def _scan() -> str | None:
            try:
                client = clamd.ClamdNetworkSocket(
                    host=self._host, port=self._port, timeout=timeout_seconds
                )
                client.ping()  # raises if unreachable
                from io import BytesIO

                result = client.instream(BytesIO(payload))
                # Result shape: {"stream": ("OK"|"FOUND", signature)}
                stream_status = result.get("stream") if isinstance(result, dict) else None
                if not stream_status:
                    return None
                status, signature = stream_status
                if status == "FOUND":
                    return str(signature)
                return None
            except Exception as exc:
                # Map any clamd error to DPAScanUnavailableError; the caller
                # treats this as "fail closed".
                raise DPAScanUnavailableError(f"clamd error: {exc}") from exc

        return await asyncio.wait_for(
            asyncio.to_thread(_scan), timeout=timeout_seconds + 1.0
        )


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


async def enumerate_dpa_paths_for_tenant(
    *,
    session: AsyncSession,
    tenant_id: UUID,
    settings: DataLifecycleSettings,
    environment: str,
) -> list[str]:
    """Return the Vault paths that hold DPA versions for a tenant.

    Used by the tenant cascade dispatch to know what Vault entries to
    delete during phase_2. The audit record is the source of truth for
    historical version listings; this function reads the active DPA
    metadata and reconstructs the path. Older versions whose Vault
    paths are not remembered on the tenant row are NOT cleaned here —
    operators retain them for the regulatory window per FR-756.5.
    """

    result = await session.execute(
        text(
            """
            SELECT slug, dpa_version, dpa_artifact_uri
            FROM tenants
            WHERE id = :tenant_id
            """
        ),
        {"tenant_id": str(tenant_id)},
    )
    row = result.mappings().first()
    if row is None:
        return []
    if row["dpa_artifact_uri"]:
        return [str(row["dpa_artifact_uri"])]
    if row["slug"] and row["dpa_version"]:
        return [
            settings.dpa_vault_path_template.format(
                env=environment, slug=row["slug"], version=row["dpa_version"]
            )
        ]
    return []
