from __future__ import annotations

from platform.common.exceptions import ValidationError
from typing import Any

from pydantic import BaseModel


class EventTypeRegistry:
    def __init__(self) -> None:
        self._schemas: dict[str, type[BaseModel]] = {}

    def register(self, event_type: str, schema: type[BaseModel]) -> None:
        self._schemas[event_type] = schema

    def validate(self, event_type: str, payload: dict[str, Any]) -> BaseModel:
        schema = self._schemas.get(event_type)
        if schema is None:
            raise ValidationError("UNKNOWN_EVENT_TYPE", f"Unregistered event type: {event_type}")
        return schema.model_validate(payload)

    def is_registered(self, event_type: str) -> bool:
        return event_type in self._schemas


event_registry = EventTypeRegistry()
