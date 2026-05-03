"""Unit tests for DPAService.

Covers:
* Clean upload — magic-bytes pass, ClamAV clean, Vault write, tenant
  row update, audit + Kafka.
* EICAR-positive upload — refused with DPAVirusDetected; no Vault
  write, no row update.
* ClamAV unreachable — DPAScanUnavailable; no Vault write.
* PDF magic-bytes mismatch and version regex refused at the door.
* Version collision — DPAVersionAlreadyExists.
* Vault write failure mapped to VaultUnreachable.
* Download — Vault read + hash verification + audit emission.
* Vault path redaction in audit + Kafka payloads (env literal stays as
  ``{env}`` placeholder; no concrete env reaches the audit chain).
"""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from platform.common.config import DataLifecycleSettings
from platform.data_lifecycle.exceptions import (
    DPAPdfInvalid,
    DPAScanUnavailable,
    DPATooLarge,
    DPAVersionAlreadyExists,
    DPAVersionNotFound,
    DPAVirusDetected,
    VaultUnreachable,
)
from platform.data_lifecycle.services.dpa_service import (
    MAX_DPA_SIZE_BYTES,
    DPAService,
)


PDF_BYTES = b"%PDF-1.7\n%fake-clean-content\n%%EOF\n"
EICAR_BYTES = (
    b"%PDF-1.7\nX5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
)
TENANT_ID = UUID("00000000-0000-0000-0000-000000000aaa")


# ---------- Stub session ----------


class _Result:
    def __init__(self, mapping: dict | None = None) -> None:
        self._mapping = mapping

    def mappings(self) -> "_Result":
        return self

    def first(self) -> dict | None:
        return self._mapping


class _StubSession:
    def __init__(
        self,
        *,
        slug: str = "acme",
        existing_version: str | None = None,
    ) -> None:
        self._slug = slug
        self._existing_version = existing_version
        self.executed: list[tuple[str, dict]] = []

    async def execute(self, sql_text, params: dict | None = None):
        params = params or {}
        sql_str = str(sql_text)
        self.executed.append((sql_str, params))
        if "FROM tenants" in sql_str and "slug" in sql_str and "dpa_version" not in sql_str:
            return _Result({"slug": self._slug})
        if "FROM tenants" in sql_str and "dpa_version" in sql_str and "dpa_artifact_uri" not in sql_str:
            return _Result({"dpa_version": self._existing_version})
        if "UPDATE tenants" in sql_str:
            return _Result(None)
        if "FROM tenants" in sql_str and "dpa_version" in sql_str:
            return _Result(
                {
                    "dpa_version": self._existing_version,
                    "dpa_signed_at": datetime.now(UTC),
                    "dpa_artifact_sha256": "deadbeef",
                    "dpa_artifact_uri": f"secret/data/musematic/test/tenants/{self._slug}/dpa/dpa-{self._existing_version}.pdf",
                }
            )
        return _Result(None)


class _StubVault:
    def __init__(self, *, fail_put: bool = False, fail_get: bool = False, payload: dict | None = None) -> None:
        self.fail_put = fail_put
        self.fail_get = fail_get
        self.stored: dict[str, dict[str, str]] = {}
        if payload:
            self.stored.update(payload)

    async def put(self, path: str, values: dict[str, str]) -> None:
        if self.fail_put:
            raise RuntimeError("vault unreachable")
        self.stored[path] = dict(values)

    async def get(self, path: str, key: str = "value", *, critical: bool = False) -> str:
        if self.fail_get:
            raise RuntimeError("vault unreachable")
        if path not in self.stored:
            raise RuntimeError("not found")
        return self.stored[path].get(key, "")

    async def delete_version(self, path: str, version: int) -> None:
        return None


class _StubScanner:
    def __init__(self, *, signature: str | None = None, raises: Exception | None = None) -> None:
        self.signature = signature
        self.raises = raises
        self.calls: list[bytes] = []

    async def scan_bytes(self, payload: bytes, *, timeout_seconds: float) -> str | None:
        self.calls.append(payload)
        if self.raises is not None:
            raise self.raises
        return self.signature


class _StubAudit:
    def __init__(self) -> None:
        self.appended: list[bytes] = []

    async def append(self, audit_event_id, namespace, canonical_payload):
        self.appended.append(canonical_payload)


class _StubProducer:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    async def publish(self, **kwargs: Any) -> None:
        self.published.append(kwargs)


def _build(
    *,
    session: _StubSession | None = None,
    vault: _StubVault | None = None,
    scanner: _StubScanner | None = None,
) -> tuple[DPAService, _StubSession, _StubVault, _StubAudit, _StubProducer]:
    session = session or _StubSession()
    vault = vault or _StubVault()
    audit = _StubAudit()
    producer = _StubProducer()
    service = DPAService(
        session=session,  # type: ignore[arg-type]
        settings=DataLifecycleSettings(),
        environment="test",
        secret_store=vault,  # type: ignore[arg-type]
        clamav_scanner=scanner,
        audit_chain=audit,  # type: ignore[arg-type]
        event_producer=producer,  # type: ignore[arg-type]
    )
    return service, session, vault, audit, producer


# ---------- Tests ----------


@pytest.mark.asyncio
async def test_clean_upload_writes_vault_and_updates_tenant() -> None:
    scanner = _StubScanner(signature=None)
    service, session, vault, audit, producer = _build(scanner=scanner)

    result = await service.upload(
        tenant_id=TENANT_ID,
        version="v3.0",
        effective_date=date(2026, 5, 3),
        pdf_bytes=PDF_BYTES,
        actor_user_id=uuid4(),
    )

    assert result.tenant_id == TENANT_ID
    assert result.version == "v3.0"
    assert result.sha256 == hashlib.sha256(PDF_BYTES).hexdigest()
    assert result.vault_path.startswith("secret/data/musematic/test/tenants/acme/dpa/")
    # ClamAV called once with the bytes.
    assert scanner.calls == [PDF_BYTES]
    # Vault stored the PDF base64-encoded plus metadata.
    stored = vault.stored[result.vault_path]
    assert base64.b64decode(stored["value"].encode("ascii")) == PDF_BYTES
    assert stored["sha256"] == result.sha256
    # Tenant row updated.
    assert any("UPDATE tenants" in q for q, _ in session.executed)
    # Audit + Kafka.
    assert any(b"dpa_uploaded" in p for p in audit.appended)
    types = [p["event_type"] for p in producer.published]
    assert "data_lifecycle.dpa.uploaded" in types
    # Audit payload uses the redacted env placeholder, not the literal env.
    found_redacted = any(b"{env}" in p for p in audit.appended)
    assert found_redacted, "audit must use redacted env placeholder"


@pytest.mark.asyncio
async def test_virus_positive_refuses_and_does_not_write_vault() -> None:
    scanner = _StubScanner(signature="Eicar-Test-Signature")
    service, session, vault, audit, producer = _build(scanner=scanner)

    with pytest.raises(DPAVirusDetected):
        await service.upload(
            tenant_id=TENANT_ID,
            version="v1.0",
            effective_date=date(2026, 5, 3),
            pdf_bytes=EICAR_BYTES,
            actor_user_id=uuid4(),
        )

    # Vault NOT written, tenant NOT updated.
    assert vault.stored == {}
    assert not any("UPDATE tenants" in q for q, _ in session.executed)
    # Rejection audited.
    assert any(b"dpa_rejected_virus" in p for p in audit.appended)


@pytest.mark.asyncio
async def test_clamav_unreachable_fails_closed() -> None:
    scanner = _StubScanner(raises=DPAScanUnavailable("clamd unreachable"))
    service, session, vault, audit, _ = _build(scanner=scanner)

    with pytest.raises(DPAScanUnavailable):
        await service.upload(
            tenant_id=TENANT_ID,
            version="v1.0",
            effective_date=date(2026, 5, 3),
            pdf_bytes=PDF_BYTES,
            actor_user_id=uuid4(),
        )

    assert vault.stored == {}
    assert not any("UPDATE tenants" in q for q, _ in session.executed)
    assert any(b"dpa_scan_unavailable" in p for p in audit.appended)


@pytest.mark.asyncio
async def test_magic_bytes_check_refuses_non_pdf() -> None:
    service, _, vault, _, _ = _build(scanner=_StubScanner())
    with pytest.raises(DPAPdfInvalid):
        await service.upload(
            tenant_id=TENANT_ID,
            version="v1.0",
            effective_date=date(2026, 5, 3),
            pdf_bytes=b"NOT-A-PDF\nrandom-content",
            actor_user_id=uuid4(),
        )
    assert vault.stored == {}


@pytest.mark.asyncio
async def test_size_limit_enforced() -> None:
    service, _, vault, _, _ = _build()
    huge = PDF_BYTES + b"\0" * (MAX_DPA_SIZE_BYTES + 1)
    with pytest.raises(DPATooLarge):
        await service.upload(
            tenant_id=TENANT_ID,
            version="v1.0",
            effective_date=date(2026, 5, 3),
            pdf_bytes=huge,
            actor_user_id=uuid4(),
        )
    assert vault.stored == {}


@pytest.mark.asyncio
async def test_version_format_validation() -> None:
    service, _, _, _, _ = _build(scanner=_StubScanner())
    with pytest.raises(DPAPdfInvalid):
        await service.upload(
            tenant_id=TENANT_ID,
            version="not-semver",
            effective_date=date(2026, 5, 3),
            pdf_bytes=PDF_BYTES,
            actor_user_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_version_collision_refused() -> None:
    session = _StubSession(existing_version="v3.0")
    service, _, vault, _, _ = _build(session=session, scanner=_StubScanner())
    with pytest.raises(DPAVersionAlreadyExists):
        await service.upload(
            tenant_id=TENANT_ID,
            version="v3.0",
            effective_date=date(2026, 5, 3),
            pdf_bytes=PDF_BYTES,
            actor_user_id=uuid4(),
        )
    assert vault.stored == {}


@pytest.mark.asyncio
async def test_vault_failure_mapped_to_vault_unreachable() -> None:
    vault = _StubVault(fail_put=True)
    service, _, _, _, _ = _build(vault=vault, scanner=_StubScanner())
    with pytest.raises(VaultUnreachable):
        await service.upload(
            tenant_id=TENANT_ID,
            version="v1.0",
            effective_date=date(2026, 5, 3),
            pdf_bytes=PDF_BYTES,
            actor_user_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_download_returns_pdf_bytes_and_audits() -> None:
    # Pre-load Vault with a DPA payload.
    sha = hashlib.sha256(PDF_BYTES).hexdigest()
    path = "secret/data/musematic/test/tenants/acme/dpa/dpa-v1.0.pdf"
    vault = _StubVault(
        payload={
            path: {
                "value": base64.b64encode(PDF_BYTES).decode("ascii"),
                "sha256": sha,
            }
        }
    )
    service, _, _, audit, _ = _build(vault=vault)
    out = await service.download(
        tenant_id=TENANT_ID, version="v1.0", actor_user_id=uuid4()
    )
    assert out == PDF_BYTES
    assert any(b"dpa_downloaded" in p for p in audit.appended)


@pytest.mark.asyncio
async def test_download_missing_version_raises_not_found() -> None:
    service, _, _, _, _ = _build()  # empty vault
    with pytest.raises(DPAVersionNotFound):
        await service.download(
            tenant_id=TENANT_ID, version="v9.9", actor_user_id=uuid4()
        )


@pytest.mark.asyncio
async def test_no_clamav_scanner_skips_with_warning() -> None:
    """In dev/test ``clamav_scanner=None`` is allowed. The service logs
    a warning but still processes the upload to a successful Vault write.
    """

    service, _, vault, audit, _ = _build(scanner=None)
    result = await service.upload(
        tenant_id=TENANT_ID,
        version="v1.0",
        effective_date=date(2026, 5, 3),
        pdf_bytes=PDF_BYTES,
        actor_user_id=uuid4(),
    )
    assert result.sha256 == hashlib.sha256(PDF_BYTES).hexdigest()
    assert result.vault_path in vault.stored
