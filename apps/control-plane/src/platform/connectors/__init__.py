from __future__ import annotations

from typing import Any

__all__ = ["get_connectors_service"]


def __getattr__(name: str) -> Any:
    if name == "get_connectors_service":
        from platform.connectors.dependencies import get_connectors_service

        return get_connectors_service
    raise AttributeError(name)
