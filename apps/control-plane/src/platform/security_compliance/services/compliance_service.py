from __future__ import annotations

import hashlib
from datetime import datetime
from platform.audit.service import AuditChainService
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.config import PlatformSettings
from platform.common.exceptions import NotFoundError
from platform.security_compliance.models import ComplianceEvidence
from platform.security_compliance.repository import SecurityComplianceRepository
from platform.security_compliance.schemas import ComplianceControlSummary
from platform.security_compliance.services._shared import canonical_json_bytes, utcnow
from typing import Any
from uuid import UUID, uuid4


class ComplianceService:
    def __init__(
        self,
        repository: SecurityComplianceRepository,
        settings: PlatformSettings,
        *,
        object_storage: AsyncObjectStorageClient | None = None,
        audit_chain: AuditChainService | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.object_storage = object_storage
        self.audit_chain = audit_chain
        self.unmapped_event_count = 0

    async def on_security_event(
        self,
        *,
        evidence_type: str,
        source: str,
        entity_id: str,
        payload: dict[str, Any],
    ) -> list[ComplianceEvidence]:
        mappings = await self.repository.list_mappings_by_evidence_type(evidence_type)
        if not mappings:
            self.unmapped_event_count += 1
            return []
        payload_hash = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        rows: list[ComplianceEvidence] = []
        for mapping in mappings:
            if mapping.filter_expression and not _filter_matches(
                payload, mapping.filter_expression
            ):
                continue
            rows.append(
                await self.repository.add(
                    ComplianceEvidence(
                        control_id=mapping.control_id,
                        evidence_type=evidence_type,
                        evidence_ref=f"{source}:{entity_id}",
                        evidence_hash=payload_hash,
                    )
                )
            )
        return rows

    async def list_frameworks(self) -> list[str]:
        controls = await self.repository.list_controls()
        return sorted({control.framework for control in controls})

    async def list_framework_controls_with_evidence(
        self,
        framework: str,
    ) -> list[ComplianceControlSummary]:
        controls = await self.repository.list_controls(framework)
        evidence = await self.repository.list_evidence_for_controls(
            [control.id for control in controls]
        )
        by_control: dict[UUID, list[ComplianceEvidence]] = {}
        for row in evidence:
            by_control.setdefault(row.control_id, []).append(row)
        return [
            ComplianceControlSummary(
                id=control.id,
                framework=control.framework,
                control_id=control.control_id,
                description=control.description,
                evidence_count=len(by_control.get(control.id, [])),
                latest_evidence_at=max(
                    (item.collected_at for item in by_control.get(control.id, [])),
                    default=None,
                ),
                gap=not by_control.get(control.id),
                suggested_source="manual attestation required"
                if not by_control.get(control.id)
                else None,
            )
            for control in controls
        ]

    async def upload_manual_evidence(
        self,
        *,
        control_id: UUID,
        description: str,
        filename: str,
        content: bytes,
        content_type: str,
        collected_by: UUID | None = None,
    ) -> ComplianceEvidence:
        control = await self.repository.get_control(control_id)
        if control is None:
            raise NotFoundError("COMPLIANCE_CONTROL_NOT_FOUND", "Compliance control not found")
        digest = hashlib.sha256(content).hexdigest()
        key = f"{control.framework}/{control_id}/{int(utcnow().timestamp())}-{filename}"
        bucket = self.settings.security_compliance.manual_evidence_bucket
        if self.object_storage is not None:
            await self.object_storage.upload_object(
                bucket,
                key,
                content,
                content_type=content_type,
                metadata={"description": description},
            )
        return await self.repository.add(
            ComplianceEvidence(
                control_id=control_id,
                evidence_type="manual",
                evidence_ref=f"s3://{bucket}/{key}",
                evidence_hash=digest,
                collected_by=collected_by,
            )
        )

    async def generate_bundle(
        self,
        *,
        framework: str,
        window_start: datetime,
        window_end: datetime,
    ) -> dict[str, Any]:
        controls = await self.repository.list_controls(framework)
        evidence = await self.repository.list_evidence_window(
            [control.id for control in controls],
            window_start=window_start,
            window_end=window_end,
        )
        bundle_id = uuid4()
        manifest = {
            "bundle_id": str(bundle_id),
            "framework": framework,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "evidence": [
                {
                    "id": str(row.id),
                    "control_id": str(row.control_id),
                    "evidence_type": row.evidence_type,
                    "evidence_ref": row.evidence_ref,
                    "evidence_hash": row.evidence_hash,
                }
                for row in evidence
            ],
        }
        payload = canonical_json_bytes(manifest)
        manifest_hash = hashlib.sha256(payload).hexdigest()
        signature = (
            self.audit_chain.signing.sign(payload).hex() if self.audit_chain is not None else ""
        )
        key = f"bundles/{framework}/{bundle_id}.json"
        bucket = self.settings.security_compliance.manual_evidence_bucket
        if self.object_storage is not None:
            await self.object_storage.upload_object(
                bucket,
                key,
                payload,
                content_type="application/json",
                metadata={"manifest_hash": manifest_hash},
            )
            url = await self.object_storage.get_presigned_url(bucket, key)
        else:
            url = f"s3://{bucket}/{key}"
        return {
            "id": bundle_id,
            "framework": framework,
            "url": url,
            "manifest_hash": manifest_hash,
            "signature": signature,
        }

    async def list_evidence(self, control_id: UUID | None = None) -> list[ComplianceEvidence]:
        return await self.repository.list_evidence(control_id)


def _filter_matches(payload: dict[str, Any], expression: str) -> bool:
    if "=" not in expression:
        return True
    key, expected = expression.split("=", 1)
    return str(payload.get(key.strip())) == expected.strip()
