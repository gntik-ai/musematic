from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.common.exceptions import NotFoundError
from platform.security_compliance.models import (
    ComplianceControl,
    ComplianceEvidence,
    ComplianceEvidenceMapping,
)
from platform.security_compliance.services.compliance_service import ComplianceService
from uuid import UUID, uuid4

import pytest


class FakeRepository:
    def __init__(self) -> None:
        self.controls: dict[UUID, ComplianceControl] = {}
        self.mappings: list[ComplianceEvidenceMapping] = []
        self.evidence: list[ComplianceEvidence] = []
        control = ComplianceControl(
            framework="soc2",
            control_id="CC6.1",
            description="Logical access is controlled.",
            evidence_requirements=["security.scan.completed"],
        )
        control.id = uuid4()
        self.controls[control.id] = control
        mapping = ComplianceEvidenceMapping(
            evidence_type="security.scan.completed",
            control_id=control.id,
            filter_expression="gating_result=passed",
        )
        mapping.id = uuid4()
        self.mappings.append(mapping)

    async def add(self, item: ComplianceEvidence) -> ComplianceEvidence:
        item.id = uuid4()
        item.collected_at = datetime.now(UTC)
        self.evidence.append(item)
        return item

    async def list_mappings_by_evidence_type(
        self,
        evidence_type: str,
    ) -> list[ComplianceEvidenceMapping]:
        return [item for item in self.mappings if item.evidence_type == evidence_type]

    async def list_controls(self, framework: str | None = None) -> list[ComplianceControl]:
        return [
            item
            for item in self.controls.values()
            if framework is None or item.framework == framework
        ]

    async def get_control(self, control_id: UUID) -> ComplianceControl | None:
        return self.controls.get(control_id)

    async def list_evidence_for_controls(
        self,
        control_ids: list[UUID],
    ) -> list[ComplianceEvidence]:
        return [item for item in self.evidence if item.control_id in control_ids]

    async def list_evidence_window(
        self,
        control_ids: list[UUID],
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> list[ComplianceEvidence]:
        return [
            item
            for item in self.evidence
            if item.control_id in control_ids and window_start <= item.collected_at <= window_end
        ]

    async def list_evidence(self, control_id: UUID | None = None) -> list[ComplianceEvidence]:
        return [
            item for item in self.evidence if control_id is None or item.control_id == control_id
        ]


class FakeObjectStorage:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, str, bytes]] = []

    async def upload_object(
        self,
        bucket: str,
        key: str,
        content: bytes,
        **_: object,
    ) -> None:
        self.uploads.append((bucket, key, content))

    async def get_presigned_url(self, bucket: str, key: str) -> str:
        return f"https://storage.test/{bucket}/{key}"


class FakeAuditSigning:
    def sign(self, document: bytes) -> bytes:
        return document[:8].ljust(64, b"0")


class FakeAuditChain:
    signing = FakeAuditSigning()


def _service(
    repository: FakeRepository,
    object_storage: FakeObjectStorage | None = None,
) -> ComplianceService:
    settings = PlatformSettings()
    return ComplianceService(
        repository,  # type: ignore[arg-type]
        settings,
        object_storage=object_storage,  # type: ignore[arg-type]
        audit_chain=FakeAuditChain(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_security_event_is_mapped_to_framework_evidence() -> None:
    repository = FakeRepository()
    service = _service(repository)

    rows = await service.on_security_event(
        evidence_type="security.scan.completed",
        source="platform.security_compliance",
        entity_id="scan-1",
        payload={"gating_result": "passed", "scanner": "bandit"},
    )
    controls = await service.list_framework_controls_with_evidence("soc2")

    assert len(rows) == 1
    assert rows[0].evidence_ref == "platform.security_compliance:scan-1"
    assert controls[0].evidence_count == 1
    assert controls[0].gap is False


@pytest.mark.asyncio
async def test_unmapped_event_increments_metric() -> None:
    service = _service(FakeRepository())

    rows = await service.on_security_event(
        evidence_type="unknown",
        source="test",
        entity_id="1",
        payload={},
    )

    assert rows == []
    assert service.unmapped_event_count == 1


@pytest.mark.asyncio
async def test_manual_upload_and_signed_bundle() -> None:
    repository = FakeRepository()
    storage = FakeObjectStorage()
    service = _service(repository, storage)
    control_id = next(iter(repository.controls))
    evidence = await service.upload_manual_evidence(
        control_id=control_id,
        description="Auditor-provided control evidence",
        filename="evidence.txt",
        content=b"manual",
        content_type="text/plain",
        collected_by=uuid4(),
    )

    bundle = await service.generate_bundle(
        framework="soc2",
        window_start=datetime.now(UTC) - timedelta(minutes=1),
        window_end=datetime.now(UTC) + timedelta(minutes=1),
    )

    assert evidence.evidence_type == "manual"
    assert storage.uploads
    assert bundle["url"].startswith("https://storage.test/")
    assert len(bundle["manifest_hash"]) == 64
    assert bundle["signature"]


@pytest.mark.asyncio
async def test_compliance_list_paths_no_storage_bundle_and_missing_control() -> None:
    repository = FakeRepository()
    service = _service(repository, object_storage=None)
    control_id = next(iter(repository.controls))
    await service.on_security_event(
        evidence_type="security.scan.completed",
        source="platform.security_compliance",
        entity_id="scan-2",
        payload={"scanner": "bandit"},
    )

    frameworks = await service.list_frameworks()
    evidence = await service.list_evidence(control_id)
    bundle = await service.generate_bundle(
        framework="soc2",
        window_start=datetime.now(UTC) - timedelta(minutes=1),
        window_end=datetime.now(UTC) + timedelta(minutes=1),
    )

    assert frameworks == ["soc2"]
    assert evidence == repository.evidence
    assert bundle["url"].startswith("s3://")

    with pytest.raises(NotFoundError):
        await service.upload_manual_evidence(
            control_id=uuid4(),
            description="missing",
            filename="missing.txt",
            content=b"missing",
            content_type="text/plain",
        )
