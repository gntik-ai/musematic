from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.security_compliance.models import VulnerabilityException, VulnerabilityScanResult
from platform.security_compliance.services.vuln_scan_service import VulnScanService
from uuid import uuid4

import pytest


class FakeRepository:
    def __init__(self) -> None:
        self.scans: list[VulnerabilityScanResult] = []
        self.exceptions: list[VulnerabilityException] = []

    async def add(self, item):
        item.id = uuid4()
        if isinstance(item, VulnerabilityScanResult):
            item.scanned_at = datetime.now(UTC)
            self.scans.append(item)
        if isinstance(item, VulnerabilityException):
            item.created_at = datetime.now(UTC)
            self.exceptions.append(item)
        return item

    async def list_scans(self, release_version: str) -> list[VulnerabilityScanResult]:
        return [item for item in self.scans if item.release_version == release_version]

    async def list_active_exceptions(
        self,
        *,
        scanner: str | None = None,
        now: datetime | None = None,
    ) -> list[VulnerabilityException]:
        cutoff = now or datetime.now(UTC)
        return [
            item
            for item in self.exceptions
            if item.expires_at > cutoff and (scanner is None or item.scanner == scanner)
        ]


@pytest.mark.asyncio
async def test_scan_ingest_blocks_critical_findings() -> None:
    repository = FakeRepository()
    service = VulnScanService(repository)  # type: ignore[arg-type]

    scan = await service.ingest_scan(
        release_version="1.0.0",
        scanner="pip_audit",
        findings=[
            {
                "vulnerability_id": "PYSEC-1",
                "component": "fastapi",
                "severity": "critical",
            }
        ],
    )

    assert scan.max_severity == "critical"
    assert scan.gating_result == "blocked"


@pytest.mark.asyncio
async def test_scan_exception_and_dev_only_findings_do_not_block() -> None:
    repository = FakeRepository()
    service = VulnScanService(repository)  # type: ignore[arg-type]
    repository.exceptions.append(
        VulnerabilityException(
            scanner="pip_audit",
            vulnerability_id="PYSEC-1",
            component_pattern="fastapi",
            justification="Temporary exception with ticket SEC-1234",
            approved_by=uuid4(),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )

    excepted = await service.ingest_scan(
        release_version="1.0.0",
        scanner="pip_audit",
        findings=[
            {
                "vulnerability_id": "PYSEC-1",
                "component": "fastapi",
                "severity": "critical",
            }
        ],
    )
    dev_only = await service.ingest_scan(
        release_version="1.0.0",
        scanner="npm_audit",
        findings=[
            {
                "vulnerability_id": "GHSA-1",
                "component": "vite",
                "severity": "high",
                "dev_only": True,
            }
        ],
    )

    assert excepted.gating_result == "passed"
    assert dev_only.gating_result == "passed"


@pytest.mark.asyncio
async def test_aggregate_status_reports_blocked_scanner() -> None:
    service = VulnScanService(FakeRepository())  # type: ignore[arg-type]
    await service.ingest_scan(
        release_version="1.0.0",
        scanner="bandit",
        findings=[
            {
                "vulnerability_id": "B101",
                "component": "src/app.py",
                "severity": "high",
            }
        ],
    )

    status = await service.evaluate_gating("1.0.0")

    assert status["gating_result"] == "blocked"
    assert status["scanners"] == ["bandit"]
    assert status["blocked_findings"][0]["scanner"] == "bandit"


@pytest.mark.asyncio
async def test_exception_create_requires_two_person_approval() -> None:
    requester = uuid4()
    service = VulnScanService(FakeRepository())  # type: ignore[arg-type]

    with pytest.raises(AuthorizationError):
        await service.create_exception(
            scanner="bandit",
            vulnerability_id="B101",
            component_pattern="*",
            justification="Temporary exception with ticket SEC-1234",
            approved_by=requester,
            requester_id=requester,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )


@pytest.mark.asyncio
async def test_vuln_scan_explicit_gating_list_exceptions_and_validation_paths() -> None:
    service = VulnScanService(FakeRepository())  # type: ignore[arg-type]
    scan = await service.ingest_scan(
        release_version="1.0.0",
        scanner="custom",
        findings=[],
        max_severity="info",
        gating_result="passed",
    )
    exception = await service.create_exception(
        scanner="custom",
        vulnerability_id="CVE-1",
        component_pattern="*",
        justification="Temporary exception with ticket SEC-1234",
        approved_by=uuid4(),
        requester_id=uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    active = await service.list_active_exceptions()

    assert scan.max_severity == "info"
    assert active == [exception]

    with pytest.raises(ValidationError):
        await service.create_exception(
            scanner="custom",
            vulnerability_id="CVE-2",
            component_pattern="*",
            justification="too short",
            approved_by=uuid4(),
            requester_id=uuid4(),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
