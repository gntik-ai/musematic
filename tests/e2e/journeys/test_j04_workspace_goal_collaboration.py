from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any
from uuid import UUID

import jwt
import pytest

from journeys.conftest import (
    AuthenticatedAsyncClient,
    JourneyContext,
    JourneyWsClient,
    _mint_access_token,
)
from journeys.helpers.api_waits import wait_for_workspace_access
from journeys.helpers.narrative import journey_step

JOURNEY_ID = "j04"
TIMEOUT_SECONDS = 300

# Cross-context inventory:
# - auth
# - workspaces
# - interactions
# - websocket
# - notifications


def _claims(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        options={"verify_signature": False, "verify_exp": False},
        algorithms=["HS256"],
    )



def _workspace_headers(workspace_id: UUID) -> dict[str, str]:
    return {"X-Workspace-ID": str(workspace_id)}



def _ws_event_type(event: dict[str, Any]) -> str | None:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    raw = payload.get("event_type")
    return str(raw) if raw is not None else None



def _ws_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return {}
    inner = payload.get("payload")
    return inner if isinstance(inner, dict) else {}



def _ws_goal_gid(event: dict[str, Any]) -> str | None:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    correlation = payload.get("correlation_context")
    if not isinstance(correlation, dict):
        return None
    goal_id = correlation.get("goal_id")
    return str(goal_id) if goal_id is not None else None



async def _read_ws_event(websocket: Any) -> dict[str, Any]:
    raw = await websocket.recv()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)



async def _wait_for_ws_event(
    websocket: Any,
    predicate: Callable[[dict[str, Any]], bool],
    *,
    timeout: float,
    description: str,
) -> dict[str, Any]:
    deadline = monotonic() + timeout
    observed: list[dict[str, Any]] = []
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise AssertionError(
                f"timed out waiting for websocket event: {description}; "
                f"observed={observed[-5:]}"
            )
        try:
            event = await asyncio.wait_for(_read_ws_event(websocket), timeout=remaining)
        except TimeoutError as exc:
            raise AssertionError(
                f"timed out waiting for websocket event: {description}; "
                f"observed={observed[-5:]}"
            ) from exc
        if event.get("type") != "event":
            continue
        observed.append(event)
        if predicate(event):
            return event


async def _wait_for_ws_event_set(
    websocket: Any,
    predicates: dict[str, Callable[[dict[str, Any]], bool]],
    *,
    timeout: float,
    description: str,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    deadline = monotonic() + timeout
    matched: dict[str, dict[str, Any]] = {}
    observed: list[dict[str, Any]] = []
    while set(matched) != set(predicates):
        remaining = deadline - monotonic()
        if remaining <= 0:
            missing = sorted(set(predicates) - set(matched))
            raise AssertionError(
                f"timed out waiting for websocket events: {description}; "
                f"missing={missing}; observed={observed[-5:]}"
            )
        try:
            event = await asyncio.wait_for(_read_ws_event(websocket), timeout=remaining)
        except TimeoutError as exc:
            missing = sorted(set(predicates) - set(matched))
            raise AssertionError(
                f"timed out waiting for websocket events: {description}; "
                f"missing={missing}; observed={observed[-5:]}"
            ) from exc
        if event.get("type") != "event":
            continue
        observed.append(event)
        for name, predicate in predicates.items():
            if name not in matched and predicate(event):
                matched[name] = event
                break
    return matched, observed



async def _mark_all_alerts_read(client: AuthenticatedAsyncClient) -> None:
    response = await client.get("/api/v1/me/alerts", params={"read": "unread", "limit": 20})
    response.raise_for_status()
    for item in response.json().get("items", []):
        mark_read = await client.patch(f"/api/v1/me/alerts/{item['id']}/read")
        mark_read.raise_for_status()



async def _wait_for_unread_count(
    client: AuthenticatedAsyncClient,
    *,
    expected: int,
    timeout: float = 60.0,
) -> int:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        response = await client.get("/api/v1/me/alerts/unread-count")
        response.raise_for_status()
        count = int(response.json()["count"])
        if count == expected:
            return count
        await asyncio.sleep(1.0)
    raise AssertionError(
        f"unread alert count did not reach {expected} within {timeout:.0f}s"
    )



async def _wait_for_kafka_event(
    client: AuthenticatedAsyncClient,
    *,
    topic: str,
    since: datetime,
    predicate: Callable[[dict[str, Any]], bool],
    key: str | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    deadline = monotonic() + timeout
    params: dict[str, Any] = {
        "topic": topic,
        "since": since.isoformat(),
        "limit": 200,
    }
    if key is not None:
        params["key"] = key
    while monotonic() < deadline:
        response = await client.get("/api/v1/_e2e/kafka/events", params=params)
        response.raise_for_status()
        for event in response.json().get("events", []):
            if predicate(event):
                return event
        await asyncio.sleep(1.0)
    raise AssertionError(f"kafka topic {topic!r} did not emit the expected event")


@pytest.mark.journey
@pytest.mark.j04_workspace_goal
@pytest.mark.j04_workspace_goal_collaboration
@pytest.mark.timeout(TIMEOUT_SECONDS)
@pytest.mark.asyncio
async def test_j04_workspace_goal_collaboration(
    admin_client: AuthenticatedAsyncClient,
    consumer_client: AuthenticatedAsyncClient,
    workspace_with_goal_ready: dict[str, Any],
    journey_context: JourneyContext,
    platform_ws_url: str,
) -> None:
    assert consumer_client.access_token is not None

    kafka_since = datetime.now(UTC) - timedelta(seconds=1)
    consumer_claims = _claims(consumer_client.access_token)
    consumer_user_id = UUID(str(consumer_claims["sub"]))
    consumer_email = str(consumer_claims["email"])
    workspace_id = UUID(str(workspace_with_goal_ready["workspace_id"]))
    consumer_workspace = consumer_client.clone(default_headers=_workspace_headers(workspace_id))

    membership_payload: dict[str, Any] | None = None
    settings_payload: dict[str, Any] | None = None
    goal_payload: dict[str, Any] | None = None
    conversation_payload: dict[str, Any] | None = None
    interaction_payload: dict[str, Any] | None = None
    first_message_payload: dict[str, Any] | None = None
    follow_up_payload: dict[str, Any] | None = None
    attention_payload: dict[str, Any] | None = None
    resolved_attention_payload: dict[str, Any] | None = None
    final_goal_payload: dict[str, Any] | None = None

    gid_headers: list[str] = []
    websocket = None

    goal_agents = workspace_with_goal_ready["goal_agents"]
    market_agent_fqn = str(goal_agents["market-data-agent"]["fqn"])
    risk_agent_fqn = str(goal_agents["risk-analysis-agent"]["fqn"])
    client_agent_fqn = str(goal_agents["client-advisory-agent"]["fqn"])
    notification_agent_fqn = str(goal_agents["notification-agent"]["fqn"])

    workspace_admin_token = _mint_access_token(
        user_id=consumer_user_id,
        email=consumer_email,
        role_names=["workspace_member", "workspace_admin"],
        workspace_id=workspace_id,
    )
    consumer_workspace_admin = consumer_workspace.clone()
    consumer_workspace_admin.set_bearer_token(workspace_admin_token)

    try:
        with journey_step("Collaborator signs in via Google OAuth and receives a session token"):
            assert consumer_client.refresh_token is not None
            assert consumer_claims["sub"]
            assert consumer_email.endswith("@e2e.test")

        with journey_step("Admin grants the collaborator workspace membership and admin authority"):
            membership = await admin_client.post(
                f"/api/v1/workspaces/{workspace_id}/members",
                json={"user_id": str(consumer_user_id), "role": "admin"},
            )
            membership.raise_for_status()
            membership_payload = membership.json()
            assert membership_payload["workspace_id"] == str(workspace_id)
            assert membership_payload["role"] == "admin"
            assert consumer_workspace_admin.access_token is not None
            workspace_detail_payload = await wait_for_workspace_access(consumer_workspace_admin, workspace_id)

        with journey_step("Collaborator opens the prepared workspace and sees four subscribed agents"):
            settings = await consumer_workspace_admin.get(f"/api/v1/workspaces/{workspace_id}/settings")
            settings.raise_for_status()
            settings_payload = settings.json()
            assert workspace_detail_payload["id"] == str(workspace_id)
            assert set(settings_payload["subscribed_agents"]) == set(
                workspace_with_goal_ready["subscribed_agents"]
            )
            assert len(settings_payload["subscribed_agents"]) == 4

        with journey_step("Collaborator creates a fresh workspace goal and receives a READY state with a GID"):
            created_goal = await consumer_workspace_admin.post(
                f"/api/v1/workspaces/{workspace_id}/goals",
                json={
                    "title": f"{journey_context.prefix}green-energy-collaboration",
                    "description": (
                        "Coordinate market, client, and risk perspectives for a green energy "
                        "portfolio update before the next client meeting."
                    ),
                    "auto_complete_timeout_seconds": 900,
                },
            )
            created_goal.raise_for_status()
            goal_payload = created_goal.json()
            assert goal_payload["workspace_id"] == str(workspace_id)
            assert goal_payload["status"] == "open"
            assert goal_payload["state"] == "ready"
            assert goal_payload["gid"]

        goal_id = UUID(str(goal_payload["id"]))
        goal_gid = str(goal_payload["gid"])

        with journey_step("Collaborator clears unread alerts and opens websocket auto-subscriptions"):
            await _mark_all_alerts_read(consumer_workspace_admin)
            alert_settings = await consumer_workspace_admin.put(
                "/api/v1/me/alert-settings",
                json={
                    # This journey asserts attention alerts; transition alerts add WS/inbox noise.
                    "state_transitions": ["ready_to_failed"],
                    "delivery_method": "in_app",
                    "webhook_url": None,
                },
            )
            alert_settings.raise_for_status()
            websocket = await JourneyWsClient(
                platform_ws_url,
                access_token=consumer_workspace_admin.access_token,
            ).connect()
            welcome = await _read_ws_event(websocket)
            auto_subscriptions = {
                item["channel"]: item["resource_id"]
                for item in welcome.get("auto_subscriptions", [])
            }
            assert welcome["type"] == "connection_established"
            assert auto_subscriptions["attention"] == str(consumer_user_id)
            assert auto_subscriptions["alerts"] == str(consumer_user_id)

        with journey_step("Collaborator creates a conversation and links an interaction to the goal"):
            conversation = await consumer_workspace_admin.post(
                "/api/v1/interactions/conversations",
                json={"title": "Green energy review", "metadata": {"journey": JOURNEY_ID}},
            )
            conversation.raise_for_status()
            conversation_payload = conversation.json()
            interaction = await consumer_workspace_admin.post(
                "/api/v1/interactions/",
                json={
                    "conversation_id": conversation_payload["id"],
                    "goal_id": str(goal_id),
                },
            )
            interaction.raise_for_status()
            interaction_payload = interaction.json()
            assert conversation_payload["workspace_id"] == str(workspace_id)
            assert interaction_payload["goal_id"] == str(goal_id)
            assert interaction_payload["conversation_id"] == conversation_payload["id"]

        with journey_step("Collaborator posts the first goal message and echoes the goal GID"):
            first_message = await consumer_workspace_admin.post(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
                headers={"X-Goal-Id": goal_gid},
                json={
                    "content": (
                        "Need market, risk, and client guidance for a green energy portfolio "
                        "rebalance ahead of tomorrow's review."
                    ),
                    "interaction_id": interaction_payload["id"],
                    "metadata": {"round": 1},
                },
            )
            first_message.raise_for_status()
            first_message_payload = first_message.json()
            gid_headers.append(first_message.headers["X-Goal-Id"])
            assert first_message_payload["goal_id"] == str(goal_id)
            assert first_message_payload["interaction_id"] == interaction_payload["id"]
            assert first_message_payload["participant_identity"] == str(consumer_user_id)

        with journey_step("The first goal message transitions the goal from READY to WORKING"):
            goal_detail = await consumer_workspace_admin.get(f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}")
            goal_detail.raise_for_status()
            current_goal = goal_detail.json()
            assert current_goal["id"] == str(goal_id)
            assert current_goal["gid"] == goal_gid
            assert current_goal["state"] == "working"

        with journey_step("Response decision rationale records respond for relevant agents and skip for the notifier"):
            rationale = await consumer_workspace_admin.get(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages/{first_message_payload['id']}/rationale"
            )
            rationale.raise_for_status()
            rationale_items = {item["agent_fqn"]: item for item in rationale.json()["items"]}
            assert rationale.json()["total"] == 4
            assert rationale_items[market_agent_fqn]["decision"] == "respond"
            assert rationale_items[risk_agent_fqn]["decision"] == "respond"
            assert rationale_items[client_agent_fqn]["decision"] == "respond"
            assert rationale_items[notification_agent_fqn]["decision"] == "skip"

        with journey_step("The market-data agent responds because the request is relevant to market analysis"):
            market_response = await consumer_workspace_admin.post(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
                headers={"X-Agent-FQN": market_agent_fqn, "X-Goal-Id": goal_gid},
                json={
                    "content": "Market view: green energy multiples remain supportive for the rebalance.",
                    "interaction_id": interaction_payload["id"],
                    "metadata": {"round": 1, "agent": "market-data"},
                },
            )
            market_response.raise_for_status()
            market_payload = market_response.json()
            gid_headers.append(market_response.headers["X-Goal-Id"])
            assert market_payload["participant_identity"] == market_agent_fqn
            assert "green energy" in market_payload["content"].lower()

        with journey_step("The risk-analysis agent responds because the request is relevant to hedging risk"):
            risk_response = await consumer_workspace_admin.post(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
                headers={"X-Agent-FQN": risk_agent_fqn, "X-Goal-Id": goal_gid},
                json={
                    "content": "Risk view: hedge sector concentration and keep downside limits explicit.",
                    "interaction_id": interaction_payload["id"],
                    "metadata": {"round": 1, "agent": "risk-analysis"},
                },
            )
            risk_response.raise_for_status()
            risk_payload = risk_response.json()
            gid_headers.append(risk_response.headers["X-Goal-Id"])
            assert risk_payload["participant_identity"] == risk_agent_fqn
            assert "hedge" in risk_payload["content"].lower()

        with journey_step("The client-advisory agent responds because the request is relevant to client guidance"):
            client_response = await consumer_workspace_admin.post(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
                headers={"X-Agent-FQN": client_agent_fqn, "X-Goal-Id": goal_gid},
                json={
                    "content": "Client view: emphasize timeline, liquidity, and suitability in the briefing.",
                    "interaction_id": interaction_payload["id"],
                    "metadata": {"round": 1, "agent": "client-advisory"},
                },
            )
            client_response.raise_for_status()
            client_payload = client_response.json()
            gid_headers.append(client_response.headers["X-Goal-Id"])
            assert client_payload["participant_identity"] == client_agent_fqn
            assert "client" in client_payload["content"].lower()

        with journey_step("The notification agent is skipped and does not post a goal response"):
            goal_messages = await consumer_workspace_admin.get(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
                params={"page": 1, "page_size": 20},
            )
            goal_messages.raise_for_status()
            items = goal_messages.json()["items"]
            participants = [item["participant_identity"] for item in items]
            assert notification_agent_fqn not in participants
            assert market_agent_fqn in participants
            assert risk_agent_fqn in participants
            assert client_agent_fqn in participants

        with journey_step("All first-round responses preserve the same GID header and use agent FQNs as participants"):
            assert set(gid_headers) == {goal_gid}
            assert all(":" in identity for identity in [market_agent_fqn, risk_agent_fqn, client_agent_fqn])
            assert all(item["goal_id"] == str(goal_id) for item in items)

        with journey_step("Collaborator posts a follow-up steering the team toward green energy focus"):
            follow_up = await consumer_workspace_admin.post(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
                headers={"X-Goal-Id": goal_gid},
                json={
                    "content": (
                        "Focus the recommendation on green energy, keep the client narrative concise, "
                        "and hedge the main downside scenarios."
                    ),
                    "interaction_id": interaction_payload["id"],
                    "metadata": {"round": 2},
                },
            )
            follow_up.raise_for_status()
            follow_up_payload = follow_up.json()
            gid_headers.append(follow_up.headers["X-Goal-Id"])
            assert follow_up_payload["participant_identity"] == str(consumer_user_id)
            assert follow_up_payload["interaction_id"] == interaction_payload["id"]

        with journey_step("Relevant agents incorporate the green-energy follow-up in their next responses"):
            second_rationale = await consumer_workspace_admin.get(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages/{follow_up_payload['id']}/rationale"
            )
            second_rationale.raise_for_status()
            second_items = {item["agent_fqn"]: item for item in second_rationale.json()["items"]}
            assert second_items[market_agent_fqn]["decision"] == "respond"
            assert second_items[risk_agent_fqn]["decision"] == "respond"
            assert second_items[client_agent_fqn]["decision"] == "respond"
            assert second_items[notification_agent_fqn]["decision"] == "skip"

            market_follow_up = await consumer_workspace_admin.post(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
                headers={"X-Agent-FQN": market_agent_fqn, "X-Goal-Id": goal_gid},
                json={
                    "content": "Updated market view: green energy remains constructive if we phase the entry.",
                    "interaction_id": interaction_payload["id"],
                    "metadata": {"round": 2, "agent": "market-data"},
                },
            )
            risk_follow_up = await consumer_workspace_admin.post(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
                headers={"X-Agent-FQN": risk_agent_fqn, "X-Goal-Id": goal_gid},
                json={
                    "content": "Updated risk view: hedge policy should explicitly cover green energy volatility.",
                    "interaction_id": interaction_payload["id"],
                    "metadata": {"round": 2, "agent": "risk-analysis"},
                },
            )
            client_follow_up = await consumer_workspace_admin.post(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
                headers={"X-Agent-FQN": client_agent_fqn, "X-Goal-Id": goal_gid},
                json={
                    "content": "Updated client view: frame the green energy shift as a measured portfolio refinement.",
                    "interaction_id": interaction_payload["id"],
                    "metadata": {"round": 2, "agent": "client-advisory"},
                },
            )
            market_follow_up.raise_for_status()
            risk_follow_up.raise_for_status()
            client_follow_up.raise_for_status()
            gid_headers.extend(
                [
                    market_follow_up.headers["X-Goal-Id"],
                    risk_follow_up.headers["X-Goal-Id"],
                    client_follow_up.headers["X-Goal-Id"],
                ]
            )
            assert "green energy" in market_follow_up.json()["content"].lower()
            assert "green energy" in risk_follow_up.json()["content"].lower()
            assert "green energy" in client_follow_up.json()["content"].lower()

        with journey_step("A relevant agent raises an attention request linked to the goal and interaction"):
            attention = await consumer_workspace_admin.post(
                "/api/v1/interactions/attention",
                headers={"X-Agent-FQN": market_agent_fqn, "X-Goal-Id": goal_gid},
                json={
                    "target_identity": str(consumer_user_id),
                    "urgency": "high",
                    "context_summary": "Need human confirmation before finalizing the green energy allocation.",
                    "related_interaction_id": interaction_payload["id"],
                    "related_goal_id": str(goal_id),
                },
            )
            attention.raise_for_status()
            attention_payload = attention.json()
            gid_headers.append(attention.headers["X-Goal-Id"])
            assert attention_payload["source_agent_fqn"] == market_agent_fqn
            assert attention_payload["status"] == "pending"
            assert attention_payload["related_goal_id"] == str(goal_id)

        with journey_step("WebSocket delivers the attention request with the expected payload"):
            attention_event = await _wait_for_ws_event(
                websocket,
                lambda event: event.get("channel") == "attention"
                and _ws_event_type(event) == "attention.requested"
                and _ws_goal_gid(event) == str(goal_id)
                and _ws_payload(event).get("related_goal_id") == str(goal_id),
                timeout=60.0,
                description="attention.requested",
            )
            assert _ws_goal_gid(attention_event) == str(goal_id)
            assert _ws_payload(attention_event)["urgency"] == "high"
            assert _ws_payload(attention_event)["related_goal_id"] == str(goal_id)
            assert _ws_payload(attention_event)["alert_already_created"] is True

        with journey_step("Collaborator sees the attention notification persisted in the inbox"):
            unread_count = await _wait_for_unread_count(consumer_workspace_admin, expected=1)
            unread_alerts = await consumer_workspace_admin.get(
                "/api/v1/me/alerts",
                params={"read": "unread", "limit": 10},
            )
            unread_alerts.raise_for_status()
            unread_items = unread_alerts.json()["items"]
            assert unread_count == 1
            assert unread_items[0]["alert_type"] == "attention_request"
            assert unread_items[0]["source_reference"]["id"] == attention_payload["id"]

        with journey_step("Collaborator resolves the attention request after reviewing the alert"):
            resolved_attention = await consumer_workspace_admin.post(
                f"/api/v1/interactions/attention/{attention_payload['id']}/resolve",
                json={"action": "resolve"},
            )
            resolved_attention.raise_for_status()
            resolved_attention_payload = resolved_attention.json()
            attention_list = await consumer_workspace_admin.get(
                "/api/v1/interactions/attention",
                params={"status": "resolved", "page": 1, "page_size": 10},
            )
            attention_list.raise_for_status()
            assert resolved_attention_payload["status"] == "resolved"
            assert attention_list.json()["total"] >= 1

        with journey_step("Collaborator marks the goal COMPLETE and the API rejects any subsequent goal message"):
            transition = await consumer_workspace_admin.post(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/transition",
                json={"target_state": "complete", "reason": "Human approval captured after attention review."},
            )
            blocked = await consumer_workspace_admin.post(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
                headers={"X-Goal-Id": goal_gid},
                json={
                    "content": "This follow-up should be rejected because the goal is complete.",
                    "interaction_id": interaction_payload["id"],
                },
            )
            goal_detail = await consumer_workspace_admin.get(f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}")
            transition.raise_for_status()
            goal_detail.raise_for_status()
            final_goal_payload = goal_detail.json()
            assert transition.json()["new_state"] == "complete"
            assert blocked.status_code == 409
            assert final_goal_payload["state"] == "complete"

        with journey_step("Kafka event logs preserve the same GID downstream and the final goal thread stays consistent"):
            workspaces_event = await _wait_for_kafka_event(
                admin_client,
                topic="workspaces.events",
                since=kafka_since,
                key=str(workspace_id),
                predicate=lambda event: event["payload"].get("event_type")
                == "workspaces.goal.created"
                and event["payload"].get("payload", {}).get("gid") == goal_gid
                and event["payload"].get("correlation_context", {}).get("goal_id") == goal_gid,
            )
            attention_event = await _wait_for_kafka_event(
                admin_client,
                topic="interaction.attention",
                since=kafka_since,
                key=str(consumer_user_id),
                predicate=lambda event: event["payload"].get("event_type")
                == "attention.requested"
                and event["payload"].get("payload", {}).get("related_goal_id") == str(goal_id)
                and event["payload"].get("correlation_context", {}).get("goal_id") == str(goal_id),
            )
            final_messages = await consumer_workspace_admin.get(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
                params={"page": 1, "page_size": 50},
            )
            final_messages.raise_for_status()
            final_items = final_messages.json()["items"]
            assert workspaces_event["payload"]["payload"]["goal_id"] == str(goal_id)
            assert attention_event["payload"]["payload"]["source_agent_fqn"] == market_agent_fqn
            assert set(item["goal_id"] for item in final_items) == {str(goal_id)}
            assert notification_agent_fqn not in {item["participant_identity"] for item in final_items}
            assert len(final_items) == 8
            assert set(gid_headers) == {goal_gid}
            assert final_goal_payload["gid"] == goal_gid
            assert resolved_attention_payload["related_goal_id"] == str(goal_id)
    finally:
        if websocket is not None:
            await websocket.close()
