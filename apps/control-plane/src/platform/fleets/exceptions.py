from __future__ import annotations

from platform.common.exceptions import NotFoundError, PlatformError
from uuid import UUID


class FleetError(PlatformError):
    status_code = 400


class FleetNotFoundError(NotFoundError):
    def __init__(self, fleet_id: UUID | str) -> None:
        super().__init__("FLEET_NOT_FOUND", f"Fleet {fleet_id} was not found")


class FleetStateError(FleetError):
    status_code = 409

    def __init__(self, message: str, *, code: str = "FLEET_STATE_INVALID") -> None:
        super().__init__(code, message)


class QuorumNotMetError(FleetError):
    status_code = 409

    def __init__(self, message: str = "Operation would break fleet quorum") -> None:
        super().__init__("FLEET_QUORUM_NOT_MET", message)


class FleetNameConflictError(FleetError):
    status_code = 409

    def __init__(self, name: str) -> None:
        super().__init__("FLEET_NAME_CONFLICT", f"Fleet name '{name}' already exists")
