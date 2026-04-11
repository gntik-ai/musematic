from __future__ import annotations

from platform.ws_hub.connection import ConnectionRegistry
from platform.ws_hub.fanout import KafkaFanout
from platform.ws_hub.subscription import SubscriptionRegistry
from platform.ws_hub.visibility import VisibilityFilter
from typing import cast

from fastapi import WebSocket


def get_connection_registry(websocket: WebSocket) -> ConnectionRegistry:
    return cast(ConnectionRegistry, websocket.app.state.connection_registry)


def get_subscription_registry(websocket: WebSocket) -> SubscriptionRegistry:
    return cast(SubscriptionRegistry, websocket.app.state.subscription_registry)


def get_fanout(websocket: WebSocket) -> KafkaFanout:
    return cast(KafkaFanout, websocket.app.state.fanout)


def get_visibility_filter(websocket: WebSocket) -> VisibilityFilter:
    return cast(VisibilityFilter, websocket.app.state.visibility_filter)

