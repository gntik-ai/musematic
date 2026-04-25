from __future__ import annotations

from platform.common.exceptions import PlatformError


class SecurityComplianceError(Exception):
    """Base exception for security compliance workflows."""


class SecurityComplianceConflictError(PlatformError):
    status_code = 409
