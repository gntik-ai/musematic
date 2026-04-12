from __future__ import annotations

from platform.common.exceptions import PlatformError
from uuid import UUID


class FleetLearningError(PlatformError):
    status_code = 400


class AdaptationError(FleetLearningError):
    status_code = 409

    def __init__(self, message: str, *, code: str = "FLEET_ADAPTATION_ERROR") -> None:
        super().__init__(code, message)


class TransferError(FleetLearningError):
    status_code = 409

    def __init__(self, message: str, *, code: str = "FLEET_TRANSFER_ERROR") -> None:
        super().__init__(code, message)


class IncompatibleTopologyError(FleetLearningError):
    status_code = 422

    def __init__(self, transfer_id: UUID | str, message: str) -> None:
        super().__init__(
            "FLEET_TRANSFER_INCOMPATIBLE_TOPOLOGY",
            f"Transfer {transfer_id} is incompatible with target topology: {message}",
        )
