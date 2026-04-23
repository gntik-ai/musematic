from __future__ import annotations

from datetime import datetime
from platform.ws_hub.subscription import ChannelType
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter


class SubscribeMessage(BaseModel):
    type: Literal["subscribe"]
    channel: ChannelType
    resource_id: str


class UnsubscribeMessage(BaseModel):
    type: Literal["unsubscribe"]
    channel: ChannelType
    resource_id: str


class ListSubscriptionsMessage(BaseModel):
    type: Literal["list_subscriptions"]


type ClientMessage = Annotated[
    SubscribeMessage | UnsubscribeMessage | ListSubscriptionsMessage,
    Field(discriminator="type"),
]

CLIENT_MESSAGE_ADAPTER: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


class SubscriptionInfo(BaseModel):
    channel: str
    resource_id: str
    subscribed_at: datetime
    auto: bool


class ConnectionEstablishedMessage(BaseModel):
    type: Literal["connection_established"] = "connection_established"
    connection_id: str
    user_id: str
    server_time: datetime
    auto_subscriptions: list[SubscriptionInfo]


class HeartbeatMessage(BaseModel):
    type: Literal["heartbeat"] = "heartbeat"
    server_time: datetime


class SubscriptionConfirmedMessage(BaseModel):
    type: Literal["subscription_confirmed"] = "subscription_confirmed"
    channel: str
    resource_id: str
    subscribed_at: datetime


class SubscriptionErrorMessage(BaseModel):
    type: Literal["subscription_error"] = "subscription_error"
    channel: str
    resource_id: str
    error: str
    code: str


class SubscriptionRemovedMessage(BaseModel):
    type: Literal["subscription_removed"] = "subscription_removed"
    channel: str
    resource_id: str


class SubscriptionListMessage(BaseModel):
    type: Literal["subscription_list"] = "subscription_list"
    subscriptions: list[SubscriptionInfo]


class EventMessage(BaseModel):
    type: Literal["event"] = "event"
    channel: str
    resource_id: str
    payload: dict[str, Any]
    gateway_received_at: datetime


class EventsDroppedMessage(BaseModel):
    type: Literal["events_dropped"] = "events_dropped"
    channel: str | None
    count: int
    dropped_at: datetime


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    error: str
    code: str


type ServerMessage = (
    ConnectionEstablishedMessage
    | HeartbeatMessage
    | SubscriptionConfirmedMessage
    | SubscriptionErrorMessage
    | SubscriptionRemovedMessage
    | SubscriptionListMessage
    | EventMessage
    | EventsDroppedMessage
    | ErrorMessage
)


def parse_client_message(payload: dict[str, Any]) -> ClientMessage:
    return CLIENT_MESSAGE_ADAPTER.validate_python(payload)
