from __future__ import annotations

from platform.trust.services import SAFETY_ORDER
from typing import Any


def resolve_action(triggered: list[str] | list[dict[str, Any]], policy: Any) -> str:
    if not triggered:
        return str(getattr(policy, "default_action", "flag") or "flag")

    action_map = getattr(policy, "action_map", {}) or {}
    default_action = str(getattr(policy, "default_action", "flag") or "flag")
    actions: list[str] = []
    for item in triggered:
        category = item.get("category") if isinstance(item, dict) else item
        action = action_map.get(str(category), default_action)
        actions.append(str(getattr(action, "value", action)))

    for candidate in SAFETY_ORDER:
        if candidate in actions:
            return candidate
    return default_action
