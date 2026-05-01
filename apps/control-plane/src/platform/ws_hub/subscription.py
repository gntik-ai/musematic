from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final


class ChannelType(StrEnum):
    EXECUTION = "execution"
    INTERACTION = "interaction"
    CONVERSATION = "conversation"
    WORKSPACE = "workspace"
    FLEET = "fleet"
    REASONING = "reasoning"
    CORRECTION = "correction"
    SIMULATION = "simulation"
    TESTING = "testing"
    ALERTS = "alerts"
    ATTENTION = "attention"
    PLATFORM_STATUS = "platform-status"
    ADMIN_HEALTH = "admin-health"
    ADMIN_INCIDENTS = "admin-incidents"
    ADMIN_QUEUES = "admin-queues"
    ADMIN_WARM_POOL = "admin-warm-pool"
    ADMIN_MAINTENANCE = "admin-maintenance"
    ADMIN_REGIONS = "admin-regions"


CHANNEL_TOPIC_MAP: Final[dict[ChannelType, Sequence[str]]] = {
    ChannelType.EXECUTION: ("execution.events", "workflow.runtime", "runtime.lifecycle"),
    ChannelType.INTERACTION: ("interaction.events",),
    ChannelType.CONVERSATION: ("interaction.events",),
    ChannelType.WORKSPACE: ("workspaces.events",),
    ChannelType.FLEET: ("runtime.lifecycle",),
    ChannelType.REASONING: ("runtime.reasoning",),
    ChannelType.CORRECTION: ("runtime.selfcorrection",),
    ChannelType.SIMULATION: ("simulation.events",),
    ChannelType.TESTING: ("testing.results",),
    ChannelType.ALERTS: ("monitor.alerts", "notifications.alerts"),
    ChannelType.ATTENTION: ("interaction.attention",),
    ChannelType.PLATFORM_STATUS: (
        "multi_region_ops.events",
        "incident_response.events",
        "platform.status.derived",
    ),
    ChannelType.ADMIN_HEALTH: ("admin.events", "monitor.alerts", "platform.status.derived"),
    ChannelType.ADMIN_INCIDENTS: ("admin.events", "incident_response.events"),
    ChannelType.ADMIN_QUEUES: ("admin.events", "execution.events", "workflow.runtime"),
    ChannelType.ADMIN_WARM_POOL: ("admin.events", "runtime.lifecycle"),
    ChannelType.ADMIN_MAINTENANCE: ("admin.events", "multi_region_ops.events"),
    ChannelType.ADMIN_REGIONS: ("admin.events", "multi_region_ops.events"),
}

WORKSPACE_SCOPED_CHANNELS: Final[set[ChannelType]] = {
    ChannelType.EXECUTION,
    ChannelType.INTERACTION,
    ChannelType.CONVERSATION,
    ChannelType.WORKSPACE,
    ChannelType.FLEET,
    ChannelType.REASONING,
    ChannelType.CORRECTION,
    ChannelType.SIMULATION,
    ChannelType.TESTING,
}
USER_SCOPED_GLOBAL_CHANNELS: Final[frozenset[ChannelType]] = frozenset(
    {
        ChannelType.ALERTS,
        ChannelType.ATTENTION,
        ChannelType.PLATFORM_STATUS,
    }
)
USER_SCOPED_CHANNELS: Final[frozenset[ChannelType]] = USER_SCOPED_GLOBAL_CHANNELS
ADMIN_SCOPED_CHANNELS: Final[frozenset[ChannelType]] = frozenset(
    {
        ChannelType.ADMIN_HEALTH,
        ChannelType.ADMIN_INCIDENTS,
        ChannelType.ADMIN_QUEUES,
        ChannelType.ADMIN_WARM_POOL,
        ChannelType.ADMIN_MAINTENANCE,
        ChannelType.ADMIN_REGIONS,
    }
)


def subscription_key(channel: ChannelType, resource_id: str) -> str:
    return f"{channel.value}:{resource_id}"


@dataclass(slots=True)
class Subscription:
    channel: ChannelType
    resource_id: str
    subscribed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    auto: bool = False


class SubscriptionRegistry:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[str]] = defaultdict(set)
        self._topic_refcount: dict[str, int] = defaultdict(int)
        self._conn_keys: dict[str, set[str]] = defaultdict(set)

    def subscribe(self, conn_id: str, sub: Subscription) -> list[str]:
        key = subscription_key(sub.channel, sub.resource_id)
        if key in self._conn_keys[conn_id]:
            return []

        self._conn_keys[conn_id].add(key)
        self._subscribers[key].add(conn_id)

        newly_needed: list[str] = []
        for topic in CHANNEL_TOPIC_MAP[sub.channel]:
            if self._topic_refcount[topic] == 0:
                newly_needed.append(topic)
            self._topic_refcount[topic] += 1
        return newly_needed

    def unsubscribe(self, conn_id: str, channel_key: str) -> list[str]:
        if channel_key not in self._conn_keys.get(conn_id, set()):
            return []

        self._conn_keys[conn_id].remove(channel_key)
        if not self._conn_keys[conn_id]:
            del self._conn_keys[conn_id]

        subscribers = self._subscribers[channel_key]
        subscribers.discard(conn_id)
        if not subscribers:
            del self._subscribers[channel_key]

        channel_name, _, _resource_id = channel_key.partition(":")
        channel = ChannelType(channel_name)
        no_longer_needed: list[str] = []
        for topic in CHANNEL_TOPIC_MAP[channel]:
            self._topic_refcount[topic] -= 1
            if self._topic_refcount[topic] <= 0:
                self._topic_refcount.pop(topic, None)
                no_longer_needed.append(topic)
        return no_longer_needed

    def unsubscribe_all(self, conn_id: str) -> list[str]:
        released_topics: set[str] = set()
        for key in list(self._conn_keys.get(conn_id, set())):
            released_topics.update(self.unsubscribe(conn_id, key))
        return sorted(released_topics)

    def get_subscribers(self, channel: ChannelType, resource_id: str) -> set[str]:
        return set(self._subscribers.get(subscription_key(channel, resource_id), set()))

    def get_resource_ids(self, channel: ChannelType) -> set[str]:
        prefix = f"{channel.value}:"
        return {
            key.removeprefix(prefix)
            for key in self._subscribers
            if key.startswith(prefix)
        }

    def get_active_topics(self) -> set[str]:
        return {topic for topic, refcount in self._topic_refcount.items() if refcount > 0}

    def has_workspace_scoped_subscriptions(self) -> bool:
        for keys in self._conn_keys.values():
            for key in keys:
                channel_name, _, _resource_id = key.partition(":")
                if ChannelType(channel_name) in WORKSPACE_SCOPED_CHANNELS:
                    return True
        return False
