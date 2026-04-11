from __future__ import annotations

from platform.ws_hub.subscription import (
    ChannelType,
    Subscription,
    SubscriptionRegistry,
    subscription_key,
)


def test_subscription_registry_topic_refcounts_and_subscribers() -> None:
    registry = SubscriptionRegistry()
    sub = Subscription(channel=ChannelType.EXECUTION, resource_id="resource-1")

    topics = registry.subscribe("conn-1", sub)

    assert set(topics) == {"workflow.runtime", "runtime.lifecycle"}
    assert registry.get_subscribers(ChannelType.EXECUTION, "resource-1") == {"conn-1"}
    assert registry.get_active_topics() == {"workflow.runtime", "runtime.lifecycle"}

    more_topics = registry.subscribe("conn-2", sub)

    assert more_topics == []
    assert registry.get_subscribers(ChannelType.EXECUTION, "resource-1") == {"conn-1", "conn-2"}
    assert registry.subscribe("conn-2", sub) == []

    released = registry.unsubscribe("conn-1", subscription_key(sub.channel, sub.resource_id))

    assert released == []
    assert registry.get_subscribers(ChannelType.EXECUTION, "resource-1") == {"conn-2"}

    released = registry.unsubscribe("conn-2", subscription_key(sub.channel, sub.resource_id))

    assert set(released) == {"workflow.runtime", "runtime.lifecycle"}
    assert registry.get_active_topics() == set()


def test_subscription_registry_unsubscribe_all_and_workspace_scope_detection() -> None:
    registry = SubscriptionRegistry()
    workspace_sub = Subscription(channel=ChannelType.WORKSPACE, resource_id="workspace-1")
    alerts_sub = Subscription(channel=ChannelType.ALERTS, resource_id="user-1")

    registry.subscribe("conn-1", workspace_sub)
    registry.subscribe("conn-1", alerts_sub)

    assert registry.has_workspace_scoped_subscriptions() is True

    released = registry.unsubscribe_all("conn-1")

    assert set(released) == {"workspaces.events", "monitor.alerts"}
    assert registry.has_workspace_scoped_subscriptions() is False
    assert registry.get_active_topics() == set()
    assert (
        registry.unsubscribe(
            "missing",
            subscription_key(workspace_sub.channel, workspace_sub.resource_id),
        )
        == []
    )
