from __future__ import annotations

from datetime import datetime
from fnmatch import fnmatch
from platform.audit.service import AuditChainService
from platform.common.events.producer import EventProducer
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.security_compliance.events import (
    ScanCompletedPayload,
    publish_security_compliance_event,
)
from platform.security_compliance.models import VulnerabilityException, VulnerabilityScanResult
from platform.security_compliance.repository import SecurityComplianceRepository
from platform.security_compliance.services._shared import append_audit, correlation
from typing import Any
from uuid import UUID

SEVERITY_RANK: dict[str, int] = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
SCANNER_GATE_SEVERITY: dict[str, str] = {
    "trivy": "critical",
    "gitleaks": "low",
    "pip_audit": "critical",
    "npm_audit": "high",
    "govulncheck": "high",
    "bandit": "high",
    "gosec": "high",
    "grype": "critical",
}


class VulnScanService:
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

    async def ingest_scan(
        self,
        *,
        release_version: str,
        scanner: str,
        findings: list[dict[str, Any]],
        max_severity: str | None = None,
        gating_result: str | None = None,
    ) -> VulnerabilityScanResult:
        normalized_scanner = scanner.strip().lower()
        computed_max = max_severity or _max_severity(findings)
        result = gating_result or await self._evaluate_findings(normalized_scanner, findings)
        item = await self.repository.add(
            VulnerabilityScanResult(
                release_version=release_version,
                scanner=normalized_scanner,
                findings=findings,
                max_severity=computed_max,
                gating_result=result,
            )
        )
        await publish_security_compliance_event(
            "security.scan.completed",
            ScanCompletedPayload(
                scan_id=item.id,
                release_version=item.release_version,
                scanner=item.scanner,
                max_severity=item.max_severity,
                gating_result=item.gating_result,
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
                "event": "vulnerability_scan.ingested",
                "scan_id": item.id,
                "release_version": item.release_version,
                "scanner": item.scanner,
                "max_severity": item.max_severity,
                "gating_result": item.gating_result,
            },
        )
        return item

    async def evaluate_gating(self, release_version: str) -> dict[str, Any]:
        scans = await self.repository.list_scans(release_version)
        blocked_findings: list[dict[str, Any]] = []
        for scan in scans:
            threshold = SCANNER_GATE_SEVERITY.get(scan.scanner, "high")
            for finding in scan.findings:
                if _finding_blocks(finding, threshold) and not await self._is_excepted(
                    scan.scanner, finding
                ):
                    blocked_findings.append({**finding, "scanner": scan.scanner})
        return {
            "release_version": release_version,
            "gating_result": "blocked" if blocked_findings else "passed",
            "scanners": sorted({scan.scanner for scan in scans}),
            "blocked_findings": blocked_findings,
        }

    async def create_exception(
        self,
        *,
        scanner: str,
        vulnerability_id: str,
        component_pattern: str,
        justification: str,
        approved_by: UUID,
        requester_id: UUID,
        expires_at: datetime,
    ) -> VulnerabilityException:
        if approved_by == requester_id:
            raise AuthorizationError("TWO_PERSON_APPROVAL_REQUIRED", "Requester cannot approve")
        if len(justification.strip()) < 20:
            raise ValidationError("JUSTIFICATION_TOO_SHORT", "Justification must be meaningful")
        return await self.repository.add(
            VulnerabilityException(
                scanner=scanner,
                vulnerability_id=vulnerability_id,
                component_pattern=component_pattern,
                justification=justification,
                approved_by=approved_by,
                expires_at=expires_at,
            )
        )

    async def list_active_exceptions(self) -> list[VulnerabilityException]:
        return await self.repository.list_active_exceptions()

    async def _evaluate_findings(self, scanner: str, findings: list[dict[str, Any]]) -> str:
        threshold = SCANNER_GATE_SEVERITY.get(scanner, "high")
        for finding in findings:
            if _finding_blocks(finding, threshold) and not await self._is_excepted(
                scanner, finding
            ):
                return "blocked"
        return "passed"

    async def _is_excepted(self, scanner: str, finding: dict[str, Any]) -> bool:
        if bool(finding.get("dev_only")) or bool(finding.get("excepted")):
            return True
        vulnerability_id = str(
            finding.get("vulnerability_id") or finding.get("id") or finding.get("rule_id") or ""
        )
        component = str(finding.get("component") or finding.get("package") or "")
        for exception in await self.repository.list_active_exceptions(scanner=scanner):
            if exception.vulnerability_id == vulnerability_id and fnmatch(
                component, exception.component_pattern
            ):
                return True
        return False


def _max_severity(findings: list[dict[str, Any]]) -> str | None:
    ranked = [
        str(item.get("severity", "")).lower()
        for item in findings
        if str(item.get("severity", "")).lower() in SEVERITY_RANK
    ]
    if not ranked:
        return None
    return max(ranked, key=lambda value: SEVERITY_RANK[value])


def _finding_blocks(finding: dict[str, Any], threshold: str) -> bool:
    severity = str(finding.get("severity", "")).lower()
    return SEVERITY_RANK.get(severity, -1) >= SEVERITY_RANK[threshold]
