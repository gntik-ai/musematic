from __future__ import annotations

from platform.common.exceptions import NotFoundError, PlatformError, ValidationError
from uuid import UUID


class GovernanceError(PlatformError):
    status_code = 400


class VerdictNotFoundError(NotFoundError):
    def __init__(self, verdict_id: UUID | str) -> None:
        super().__init__("VERDICT_NOT_FOUND", f"Governance verdict {verdict_id} was not found")


class ChainConfigError(ValidationError):
    def __init__(self, message: str, *, code: str = "CHAIN_VALIDATION_ERROR") -> None:
        super().__init__(code, message)
