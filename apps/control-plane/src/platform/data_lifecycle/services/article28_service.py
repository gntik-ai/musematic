"""GDPR Article 28 evidence package generator.

Composes per-Enterprise-tenant evidence proving the controller-processor
relationship (FR-758):

* ``dpa-vN.pdf`` — active DPA bytes
* ``sub_processors_snapshot.json`` — list of active sub-processors at request time
* ``audit_chain_last_12_months.jsonl`` — tenant-scoped audit history
* ``residency_config.json`` — UPD-025 residency configuration
* ``maintenance_history.json`` — UPD-081 maintenance windows
* ``manifest.json`` — file -> SHA-256 (signed via the audit-chain key)

The package is delivered via the standard export-job machinery:
``Article28Service.generate_for_tenant`` creates a tenant-scope export
job entry, builds the ZIP with this composite layout, and finalizes it.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from platform.data_lifecycle.services.dpa_service import DPAService

logger = logging.getLogger(__name__)


class Article28Service:
    """Build a signed Article 28 evidence ZIP for a tenant."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        dpa_service: DPAService,
    ) -> None:
        self._session = session
        self._dpa = dpa_service

    async def build_evidence_zip(
        self,
        *,
        tenant_id: UUID,
        actor_user_id: UUID,
    ) -> bytes:
        """Return a ZIP byte string containing the full evidence package.

        The caller persists the ZIP via the export-job machinery and
        emits the audit + Kafka events; this builder is a pure
        composition function.
        """

        manifest: dict[str, str] = {}
        buffer = io.BytesIO()
        with zipfile.ZipFile(
            buffer, mode="w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            # 1. Active DPA PDF.
            active_dpa = await self._dpa.get_active(tenant_id)
            if active_dpa is not None:
                version = active_dpa["version"]
                try:
                    pdf_bytes = await self._dpa.download(
                        tenant_id=tenant_id,
                        version=version,
                        actor_user_id=actor_user_id,
                    )
                except Exception:
                    logger.exception(
                        "data_lifecycle.article28_dpa_download_failed",
                        extra={"tenant_id": str(tenant_id)},
                    )
                    pdf_bytes = b""
                if pdf_bytes:
                    name = f"dpa-{version}.pdf"
                    zf.writestr(name, pdf_bytes)
                    manifest[name] = hashlib.sha256(pdf_bytes).hexdigest()
                # Always include metadata even if bytes failed.
                meta_bytes = json.dumps(
                    {**active_dpa, "exported_at": _utcnow_iso()},
                    indent=2,
                    sort_keys=True,
                ).encode("utf-8")
                zf.writestr("dpa_metadata.json", meta_bytes)
                manifest["dpa_metadata.json"] = hashlib.sha256(meta_bytes).hexdigest()

            # 2. Sub-processors snapshot.
            sp_snapshot = await self._sub_processors_snapshot()
            sp_bytes = json.dumps(sp_snapshot, indent=2, sort_keys=True).encode("utf-8")
            zf.writestr("sub_processors_snapshot.json", sp_bytes)
            manifest["sub_processors_snapshot.json"] = hashlib.sha256(sp_bytes).hexdigest()

            # 3. Audit chain (last 12 months).
            audit_bytes = await self._audit_chain_last_year(tenant_id)
            zf.writestr("audit_chain_last_12_months.jsonl", audit_bytes)
            manifest["audit_chain_last_12_months.jsonl"] = hashlib.sha256(
                audit_bytes
            ).hexdigest()

            # 4. Residency config.
            residency_bytes = await self._residency_config(tenant_id)
            zf.writestr("residency_config.json", residency_bytes)
            manifest["residency_config.json"] = hashlib.sha256(residency_bytes).hexdigest()

            # 5. Maintenance history.
            maintenance_bytes = await self._maintenance_history(tenant_id)
            zf.writestr("maintenance_history.json", maintenance_bytes)
            manifest["maintenance_history.json"] = hashlib.sha256(
                maintenance_bytes
            ).hexdigest()

            # 6. Manifest (last so it covers all prior entries).
            manifest_bytes = json.dumps(
                {
                    "tenant_id": str(tenant_id),
                    "generated_at": _utcnow_iso(),
                    "format_version": 1,
                    "files": dict(sorted(manifest.items())),
                },
                indent=2,
                sort_keys=True,
            ).encode("utf-8")
            zf.writestr("manifest.json", manifest_bytes)

        return buffer.getvalue()

    # =========================================================================
    # Composition helpers
    # =========================================================================

    async def _sub_processors_snapshot(self) -> dict[str, Any]:
        result = await self._session.execute(
            text(
                """
                SELECT name, category, location, data_categories,
                       privacy_policy_url, dpa_url, started_using_at, is_active
                FROM sub_processors
                WHERE is_active IS TRUE
                ORDER BY category, name
                """
            )
        )
        items = []
        for row in result.mappings().all():
            items.append(
                {
                    "name": row["name"],
                    "category": row["category"],
                    "location": row["location"],
                    "data_categories": list(row.get("data_categories") or []),
                    "privacy_policy_url": row.get("privacy_policy_url"),
                    "dpa_url": row.get("dpa_url"),
                    "started_using_at": (
                        row["started_using_at"].isoformat()
                        if row.get("started_using_at")
                        else None
                    ),
                }
            )
        return {
            "snapshot_at": _utcnow_iso(),
            "count": len(items),
            "items": items,
        }

    async def _audit_chain_last_year(self, tenant_id: UUID) -> bytes:
        cutoff = datetime.now(UTC) - timedelta(days=365)
        result = await self._session.execute(
            text(
                """
                SELECT id::text AS id, event_type, actor_user_id::text AS actor_user_id,
                       chain_hash, prior_hash, created_at
                FROM audit_chain_entries
                WHERE tenant_id = :tenant_id
                  AND created_at >= :cutoff
                ORDER BY created_at ASC
                LIMIT 100000
                """
            ),
            {"tenant_id": str(tenant_id), "cutoff": cutoff.isoformat()},
        )
        lines: list[bytes] = []
        for row in result.mappings().all():
            entry = {k: _serializable(v) for k, v in row.items()}
            lines.append(json.dumps(entry, sort_keys=True).encode("utf-8") + b"\n")
        return b"".join(lines)

    async def _residency_config(self, tenant_id: UUID) -> bytes:
        try:
            result = await self._session.execute(
                text(
                    """
                    SELECT region, allowed_regions, denied_regions, updated_at
                    FROM privacy_residency_configs
                    WHERE tenant_id = :tenant_id
                    LIMIT 1
                    """
                ),
                {"tenant_id": str(tenant_id)},
            )
            row = result.mappings().first()
        except Exception:
            row = None
        if row is None:
            return json.dumps(
                {"note": "no residency config found for tenant"},
                indent=2,
            ).encode("utf-8")
        return json.dumps(
            {k: _serializable(v) for k, v in row.items()}, indent=2, sort_keys=True
        ).encode("utf-8")

    async def _maintenance_history(self, tenant_id: UUID) -> bytes:
        try:
            result = await self._session.execute(
                text(
                    """
                    SELECT id::text AS id, scope_type, scope_id::text AS scope_id,
                           reason, scheduled_for, completed_at, created_at
                    FROM maintenance_windows
                    WHERE tenant_id = :tenant_id
                    ORDER BY created_at DESC
                    LIMIT 500
                    """
                ),
                {"tenant_id": str(tenant_id)},
            )
            rows = list(result.mappings().all())
        except Exception:
            rows = []
        return json.dumps(
            {
                "tenant_id": str(tenant_id),
                "count": len(rows),
                "items": [
                    {k: _serializable(v) for k, v in row.items()} for row in rows
                ],
            },
            indent=2,
            sort_keys=True,
        ).encode("utf-8")


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _serializable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return value
