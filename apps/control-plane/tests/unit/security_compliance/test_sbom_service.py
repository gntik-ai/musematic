from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from platform.common.exceptions import NotFoundError
from platform.security_compliance.exceptions import SecurityComplianceConflictError
from platform.security_compliance.models import SoftwareBillOfMaterials
from platform.security_compliance.services.sbom_service import SbomService
from uuid import uuid4

import pytest


class FakeRepository:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], SoftwareBillOfMaterials] = {}

    async def add(self, item: SoftwareBillOfMaterials) -> SoftwareBillOfMaterials:
        item.id = uuid4()
        item.generated_at = datetime.now(UTC)
        self.items[(item.release_version, item.format)] = item
        return item

    async def get_sbom(
        self,
        release_version: str,
        sbom_format: str,
    ) -> SoftwareBillOfMaterials | None:
        return self.items.get((release_version, sbom_format))


@pytest.mark.asyncio
async def test_sbom_ingest_computes_hash_and_persists() -> None:
    repository = FakeRepository()
    service = SbomService(repository)  # type: ignore[arg-type]

    result = await service.ingest(
        release_version="1.4.0",
        sbom_format="cyclonedx",
        content='{"bomFormat":"CycloneDX"}',
    )

    assert result.format == "cyclonedx"
    assert result.content_sha256 == hashlib.sha256(result.content.encode()).hexdigest()
    assert await repository.get_sbom("1.4.0", "cyclonedx") is result


@pytest.mark.asyncio
async def test_sbom_duplicate_is_conflict() -> None:
    service = SbomService(FakeRepository())  # type: ignore[arg-type]

    await service.ingest(release_version="1.4.0", sbom_format="spdx", content='{"spdx":true}')

    with pytest.raises(SecurityComplianceConflictError):
        await service.ingest(
            release_version="1.4.0",
            sbom_format="spdx",
            content='{"spdx":true}',
        )


@pytest.mark.asyncio
async def test_sbom_retrieve_and_hash_mismatch_detection() -> None:
    service = SbomService(FakeRepository())  # type: ignore[arg-type]
    stored = await service.ingest(
        release_version="1.4.0",
        sbom_format="spdx",
        content='{"name":"before"}',
    )
    stored.content = '{"name":"after"}'

    assert await service.get("1.4.0", "spdx") is stored
    digest, valid = await service.get_hash("1.4.0", "spdx")
    assert digest == stored.content_sha256
    assert valid is False


@pytest.mark.asyncio
async def test_sbom_missing_raises_not_found() -> None:
    service = SbomService(FakeRepository())  # type: ignore[arg-type]

    with pytest.raises(NotFoundError):
        await service.get("missing", "spdx")
