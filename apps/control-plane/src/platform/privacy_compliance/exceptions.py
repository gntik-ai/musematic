from __future__ import annotations

from platform.common.exceptions import (
    AuthorizationError,
    NotFoundError,
    PlatformError,
    ValidationError,
)
from uuid import UUID


class PrivacyComplianceError(PlatformError):
    """Base error for the privacy compliance bounded context."""


class DSRNotFoundError(NotFoundError):
    def __init__(self, dsr_id: UUID) -> None:
        super().__init__("PRIVACY_DSR_NOT_FOUND", "DSR request not found", {"dsr_id": str(dsr_id)})


class TombstoneNotFoundError(NotFoundError):
    def __init__(self, tombstone_id: UUID) -> None:
        super().__init__(
            "PRIVACY_TOMBSTONE_NOT_FOUND",
            "Deletion tombstone not found",
            {"tombstone_id": str(tombstone_id)},
        )


class CascadePartialFailure(PrivacyComplianceError):  # noqa: N818
    status_code = 500

    def __init__(self, tombstone: object, errors: list[str]) -> None:
        super().__init__(
            "PRIVACY_CASCADE_PARTIAL_FAILURE",
            "Cascade deletion completed with one or more store failures",
            {"tombstone_id": str(getattr(tombstone, "id", "")), "errors": errors},
        )
        self.tombstone = tombstone
        self.errors = errors


class ConsentRequired(PrivacyComplianceError):  # noqa: N818
    status_code = 428

    def __init__(self, missing_types: list[str]) -> None:
        super().__init__(
            "PRIVACY_CONSENT_REQUIRED",
            "Consent choices are required before continuing",
            {
                "missing_consents": missing_types,
                "disclosure_text_ref": "/api/v1/me/consents/disclosure",
            },
        )
        self.missing_types = missing_types


class PIAApprovalError(AuthorizationError):
    def __init__(self) -> None:
        super().__init__(
            "PRIVACY_PIA_APPROVER_MUST_DIFFER",
            "PIA approver must differ from submitter",
        )


class ResidencyViolation(AuthorizationError):  # noqa: N818
    def __init__(
        self,
        *,
        workspace_id: UUID,
        origin_region: str,
        required_region: str,
        allowed_transfer_regions: list[str],
    ) -> None:
        super().__init__(
            "PRIVACY_RESIDENCY_VIOLATION",
            "Request origin region violates workspace residency policy",
            {
                "workspace_id": str(workspace_id),
                "origin_region": origin_region,
                "required_region": required_region,
                "allowed_transfer_regions": allowed_transfer_regions,
            },
        )


class ToolOutputBlocked(AuthorizationError):  # noqa: N818
    def __init__(self, summaries: list[str]) -> None:
        super().__init__(
            "PRIVACY_DLP_BLOCKED",
            "DLP policy blocked tool output",
            {"matches": summaries},
        )


class SeededRuleDeletionError(ValidationError):
    status_code = 403

    def __init__(self) -> None:
        super().__init__(
            "PRIVACY_DLP_SEEDED_RULE_DELETE_FORBIDDEN",
            "Seeded DLP rules cannot be deleted",
        )
