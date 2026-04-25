from __future__ import annotations

import hashlib
from platform.audit.service import AuditChainService
from platform.common.events.producer import EventProducer
from platform.common.exceptions import NotFoundError, ValidationError
from platform.security_compliance.events import (
    SbomPublishedPayload,
    publish_security_compliance_event,
)
from platform.security_compliance.exceptions import SecurityComplianceConflictError
from platform.security_compliance.models import SoftwareBillOfMaterials
from platform.security_compliance.repository import SecurityComplianceRepository
from platform.security_compliance.services._shared import append_audit, correlation


class SbomService:
    def __init__(
        self,
        repository: SecurityComplianceRepository,
        *,
        producer: EventProducer | None = None,
        audit_chain: AuditChainService | None = None,
    ) -> None:
        self.repository = repository
        self.producer = producer
        self.audit_chain = audit_chain

    async def ingest(
        self,
        *,
        release_version: str,
        sbom_format: str,
        content: str,
    ) -> SoftwareBillOfMaterials:
        normalized_format = sbom_format.strip().lower()
        if normalized_format not in {"spdx", "cyclonedx"}:
            raise ValidationError("INVALID_SBOM_FORMAT", "Unsupported SBOM format")
        existing = await self.repository.get_sbom(release_version, normalized_format)
        if existing is not None:
            raise SecurityComplianceConflictError(
                "SBOM_EXISTS",
                "SBOM already exists for this release and format",
            )
        item = await self.repository.add(
            SoftwareBillOfMaterials(
                release_version=release_version,
                format=normalized_format,
                content=content,
                content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            )
        )
        await publish_security_compliance_event(
            "security.sbom.published",
            SbomPublishedPayload(
                sbom_id=item.id,
                release_version=item.release_version,
                format=item.format,
                content_sha256=item.content_sha256,
            ),
            correlation(),
            self.producer,
            key=item.release_version,
        )
        await append_audit(
            self.audit_chain,
            item.id,
            "security_compliance",
            {
                "event": "sbom.ingested",
                "sbom_id": item.id,
                "release_version": item.release_version,
                "format": item.format,
                "content_sha256": item.content_sha256,
            },
        )
        return item

    async def get(self, release_version: str, sbom_format: str) -> SoftwareBillOfMaterials:
        item = await self.repository.get_sbom(release_version, sbom_format.strip().lower())
        if item is None:
            raise NotFoundError("SBOM_NOT_FOUND", "SBOM not found")
        return item

    async def get_hash(self, release_version: str, sbom_format: str) -> tuple[str, bool]:
        item = await self.get(release_version, sbom_format)
        current = hashlib.sha256(item.content.encode("utf-8")).hexdigest()
        return item.content_sha256, current == item.content_sha256
