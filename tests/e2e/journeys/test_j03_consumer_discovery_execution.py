from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from time import monotonic
from typing import Any
from uuid import UUID

import jwt
import pytest

from journeys.conftest import (
    AuthenticatedAsyncClient,
    JourneyContext,
    JourneyWsClient,
    _workflow_yaml,
)
from journeys.helpers.api_waits import wait_for_workspace_access
from journeys.helpers.executions import wait_for_execution
from journeys.helpers.narrative import journey_step
from journeys.helpers.websockets import assert_event_order, subscribe_ws

JOURNEY_ID = "j03"
TIMEOUT_SECONDS = 300

# Cross-context inventory:
# - auth
# - marketplace
# - interactions
# - workflows
# - execution
# - reasoning
# - context-engineering
# - websocket


def _claims(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        options={"verify_signature": False, "verify_exp": False},
        algorithms=["HS256"],
    )



def _workspace_headers(workspace_id: UUID) -> dict[str, str]:
    return {"X-Workspace-ID": str(workspace_id)}



def _role_names(claims: dict[str, Any]) -> set[str]:
    return {
        str(item.get("role"))
        for item in claims.get("roles", [])
        if isinstance(item, dict) and item.get("role") is not None
    }



def _find_marketplace_result(payload: dict[str, Any], agent_id: str) -> dict[str, Any] | None:
    for item in payload.get("results", []):
        if item.get("agent_id") == agent_id:
            return item
    return None



def _gateway_event_type(event: dict[str, Any]) -> str:
    payload = event.get("payload")
    if isinstance(payload, dict) and payload.get("event_type") is not None:
        return str(payload["event_type"])
    return str(event.get("type"))



def _gateway_inner_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return {}
    inner = payload.get("payload")
    return inner if isinstance(inner, dict) else {}



def _execution_status(event: dict[str, Any]) -> str | None:
    status = _gateway_inner_payload(event).get("status")
    return str(status) if status is not None else None



def _reasoning_step_id(event: dict[str, Any]) -> str | None:
    step_id = _gateway_inner_payload(event).get("step_id")
    return str(step_id) if step_id is not None else None



def _status_projection(events: list[dict[str, Any]]) -> list[dict[str, str]]:
    projected: list[dict[str, str]] = []
    for event in events:
        status = _execution_status(event)
        if status is not None:
            projected.append({"type": status})
    return projected



async def _wait_for_marketplace_search_result(
    client: AuthenticatedAsyncClient,
    *,
    query: str,
    agent_id: str,
    timeout: float = 60.0,
) -> dict[str, Any]:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        response = await client.post(
            "/api/v1/marketplace/search",
            json={"query": query, "page": 1, "page_size": 10},
        )
        response.raise_for_status()
        payload = response.json()
        if _find_marketplace_result(payload, agent_id) is not None:
            return payload
        await asyncio.sleep(1.0)
    raise AssertionError(
        f"marketplace query {query!r} did not return agent {agent_id} within {timeout:.0f}s"
    )



async def _wait_for_ws_event(
    events: AsyncIterator[dict[str, Any]],
    predicate: Callable[[dict[str, Any]], bool],
    *,
    timeout: float,
    description: str,
) -> dict[str, Any]:
    deadline = monotonic() + timeout
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise AssertionError(f"timed out waiting for websocket event: {description}")
        event = await asyncio.wait_for(anext(events), timeout=remaining)
        if predicate(event):
            return event



async def _mark_all_alerts_read(
    client: AuthenticatedAsyncClient,
    *,
    timeout: float = 30.0,
) -> None:
    deadline = monotonic() + timeout
    while True:
        response = await client.get("/api/v1/me/alerts", params={"read": "unread", "limit": 100})
        response.raise_for_status()
        for item in response.json().get("items", []):
            mark_read = await client.patch(f"/api/v1/me/alerts/{item['id']}/read")
            mark_read.raise_for_status()

        count_response = await client.get("/api/v1/me/alerts/unread-count")
        count_response.raise_for_status()
        if int(count_response.json()["count"]) == 0:
            return
        if monotonic() >= deadline:
            raise AssertionError(
                f"unread alerts did not clear within {timeout:.0f}s; "
                f"last count={count_response.json()['count']}"
            )
        await asyncio.sleep(1.0)



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


@pytest.mark.journey
@pytest.mark.j03_consumer
@pytest.mark.j03_consumer_discovery_execution
@pytest.mark.timeout(TIMEOUT_SECONDS)
@pytest.mark.parametrize("signup_method", ["oauth_google"])
@pytest.mark.asyncio
async def test_j03_consumer_discovery_execution(
    admin_client: AuthenticatedAsyncClient,
    consumer_client: AuthenticatedAsyncClient,
    published_agent: dict[str, Any],
    journey_context: JourneyContext,
    platform_ws_url: str,
    signup_method: str,
) -> None:
    assert consumer_client.access_token is not None
    assert signup_method == "oauth_google"

    consumer_claims = _claims(consumer_client.access_token)
    consumer_user_id = UUID(str(consumer_claims["sub"]))
    workspace_id = UUID(str(published_agent["workspace_id"]))
    agent_id = str(published_agent["id"])
    admin_workspace = admin_client.clone(default_headers=_workspace_headers(workspace_id))
    consumer_workspace = consumer_client.clone(default_headers=_workspace_headers(workspace_id))

    browse_payload: dict[str, Any] | None = None
    intent_payload: dict[str, Any] | None = None
    listing_payload: dict[str, Any] | None = None
    quality_payload: dict[str, Any] | None = None
    conversation_payload: dict[str, Any] | None = None
    first_interaction: dict[str, Any] | None = None
    second_interaction: dict[str, Any] | None = None
    workflow_payload: dict[str, Any] | None = None
    first_execution_payload: dict[str, Any] | None = None
    second_execution_payload: dict[str, Any] | None = None
    first_reasoning_step_id: str | None = None

    with journey_step("Consumer signs in via Google OAuth and receives a session token"):
        assert consumer_client.refresh_token is not None
        assert consumer_claims["sub"]
        assert consumer_claims["email"].endswith("@e2e.test")

    with journey_step("Google sign-in yields a provisioned consumer with the default role"):
        role_names = _role_names(consumer_claims)
        links = await consumer_client.get("/api/v1/auth/oauth/links")
        audit = await admin_client.get(
            "/api/v1/admin/oauth/audit",
            params={"provider_type": "google", "user_id": str(consumer_user_id), "limit": 20},
        )
        links.raise_for_status()
        audit.raise_for_status()
        actions = {item["action"] for item in audit.json()["items"]}
        assert "workspace_member" in role_names
        assert any(item["provider_type"] == "google" for item in links.json()["items"])
        assert "sign_in_succeeded" in actions

    with journey_step("Admin grants the consumer access to the published-agent workspace and tunes listing metadata"):
        membership = await admin_client.post(
            f"/api/v1/workspaces/{workspace_id}/members",
            json={"user_id": str(consumer_user_id), "role": "member"},
        )
        patch = await admin_workspace.patch(
            f"/api/v1/agents/{agent_id}",
            json={
                "display_name": "Customer Identity Verifier",
                "purpose": (
                    "Verify customer identity evidence, review onboarding packages, and "
                    "summarize KYC compliance findings with deterministic explanations."
                ),
                "approach": (
                    "Deterministic customer-identity verification with structured checklist "
                    "reviews, provenance-aware reasoning, and explicit escalation notes."
                ),
                "tags": ["kyc", "identity", "verification"],
                "visibility_agents": ["*"],
                "visibility_tools": ["*"],
            },
        )
        membership.raise_for_status()
        patch.raise_for_status()
        assert membership.json()["workspace_id"] == str(workspace_id)
        assert patch.json()["display_name"] == "Customer Identity Verifier"
        await wait_for_workspace_access(consumer_workspace, workspace_id)

    with journey_step("Admin classifies the published agent and verifies tag plus label catalog filtering"):
        tag = await admin_workspace.post(
            f"/api/v1/tags/agent/{agent_id}",
            json={"tag": f"{JOURNEY_ID}-verified"},
        )
        label = await admin_workspace.post(
            f"/api/v1/labels/agent/{agent_id}",
            json={"key": "env", "value": "production"},
        )
        filtered = await admin_workspace.get(
            "/api/v1/agents",
            params={"tags": f"{JOURNEY_ID}-verified", "label.env": "production"},
        )
        tag.raise_for_status()
        label.raise_for_status()
        filtered.raise_for_status()
        assert agent_id in {item["id"] for item in filtered.json()["items"]}

    with journey_step("Consumer browses the marketplace home within the workspace scope"):
        browse_payload = await _wait_for_marketplace_search_result(
            consumer_workspace,
            query="",
            agent_id=agent_id,
        )
        assert browse_payload["has_results"] is True
        assert _find_marketplace_result(browse_payload, agent_id) is not None

    with journey_step('Consumer searches by intent "verify customer identity"'):
        intent_payload = await _wait_for_marketplace_search_result(
            consumer_workspace,
            query="verify customer identity",
            agent_id=agent_id,
        )
        assert intent_payload["query"] == "verify customer identity"
        assert intent_payload["has_results"] is True

    with journey_step("Marketplace search ranks the published agent with trust and relevance data"):
        assert intent_payload is not None
        agent_result = _find_marketplace_result(intent_payload, agent_id)
        assert agent_result is not None
        assert agent_result["agent_id"] == agent_id
        assert agent_result["relevance_score"] is not None
        assert agent_result["status"] == "published"
        assert agent_result["certification_status"] != "uncertified"

    with journey_step("Consumer inspects the published agent profile with FQN, purpose, and trust badges"):
        listing = await consumer_workspace.get(f"/api/v1/marketplace/agents/{agent_id}")
        listing.raise_for_status()
        listing_payload = listing.json()
        assert listing_payload["agent_id"] == agent_id
        assert ":" in listing_payload["fqn"]
        assert listing_payload["certification_status"] != "uncertified"
        assert listing_payload["description"]

    with journey_step("Consumer inspects the quality profile exposed on the marketplace listing"):
        quality = await consumer_workspace.get(f"/api/v1/marketplace/agents/{agent_id}/quality")
        quality.raise_for_status()
        quality_payload = quality.json()
        assert quality_payload["certification_compliance"] != "uncertified"
        assert isinstance(quality_payload["has_data"], bool)
        assert "satisfaction_count" in quality_payload

    with journey_step("Consumer starts a new conversation for the identity-verification task"):
        conversation = await consumer_workspace.post(
            "/api/v1/interactions/conversations",
            json={
                "title": f"{journey_context.prefix}identity-review",
                "metadata": {"journey_id": JOURNEY_ID},
            },
        )
        conversation.raise_for_status()
        conversation_payload = conversation.json()
        assert conversation_payload["workspace_id"] == str(workspace_id)
        assert conversation_payload["title"].endswith("identity-review")

    with journey_step("Conversation detail returns the new conversation identifier and zero initial messages"):
        assert conversation_payload is not None
        conversation_id = UUID(str(conversation_payload["id"]))
        detail = await consumer_workspace.get(f"/api/v1/interactions/conversations/{conversation_id}")
        listed = await consumer_workspace.get("/api/v1/interactions/conversations")
        detail.raise_for_status()
        listed.raise_for_status()
        assert detail.json()["id"] == str(conversation_id)
        assert detail.json()["message_count"] == 0
        assert any(item["id"] == str(conversation_id) for item in listed.json()["items"])

    with journey_step("Consumer opens the first interaction and transitions it to a running state"):
        assert conversation_payload is not None
        first_interaction_response = await consumer_workspace.post(
            "/api/v1/interactions/",
            json={"conversation_id": conversation_payload["id"]},
        )
        first_interaction_response.raise_for_status()
        first_interaction = first_interaction_response.json()
        ready = await consumer_workspace.post(
            f"/api/v1/interactions/{first_interaction['id']}/transition",
            json={"trigger": "ready"},
        )
        started = await consumer_workspace.post(
            f"/api/v1/interactions/{first_interaction['id']}/transition",
            json={"trigger": "start"},
        )
        ready.raise_for_status()
        started.raise_for_status()
        assert started.json()["state"] == "running"
        assert started.json()["conversation_id"] == conversation_payload["id"]

    with journey_step("Consumer sends the first task message into the conversation"):
        assert first_interaction is not None
        first_message = await consumer_workspace.post(
            f"/api/v1/interactions/{first_interaction['id']}/messages",
            json={"content": "Verify customer identity documents and summarize any KYC gaps."},
        )
        first_messages = await consumer_workspace.get(
            f"/api/v1/interactions/{first_interaction['id']}/messages"
        )
        first_message.raise_for_status()
        first_messages.raise_for_status()
        assert first_message.json()["message_type"] == "user"
        assert first_messages.json()["total"] == 1

    with journey_step("Admin provisions a single-step workflow bound to the published agent"):
        workflow = await admin_workspace.post(
            "/api/v1/workflows",
            json={
                "name": f"{journey_context.prefix}consumer-identity-verification",
                "description": "Journey workflow used for consumer discovery and execution coverage.",
                "yaml_source": _workflow_yaml(str(published_agent["fqn"])),
                "tags": ["journey", JOURNEY_ID, "consumer"],
                "workspace_id": str(workspace_id),
            },
        )
        workflow.raise_for_status()
        workflow_payload = workflow.json()
        assert workflow_payload["workspace_id"] == str(workspace_id)
        assert workflow_payload["name"].endswith("consumer-identity-verification")

    conversation_ws_client = JourneyWsClient(platform_ws_url, access_token=consumer_client.access_token)
    async with subscribe_ws(conversation_ws_client, "conversation", conversation_payload["id"]) as conversation_subscription:
        conversation_events = conversation_subscription.events()

        with journey_step("Consumer subscribes to conversation-scoped websocket updates"):
            assert conversation_subscription.channel == "conversation"
            assert conversation_subscription.resource_id == conversation_payload["id"]
            assert conversation_subscription.received_events == []

        first_mock = await admin_client.post(
            "/api/v1/_e2e/mock-llm/set-response",
            json={
                "prompt_pattern": "agent_response",
                "response": "Customer identity verified. Passport, selfie, and proof-of-address passed deterministic checks.",
                "streaming_chunks": ["Customer identity verified.", " Passport, selfie, and proof-of-address passed.", " Deterministic checks completed."],
            },
        )
        first_mock.raise_for_status()
        first_execution = await consumer_workspace.post(
            "/api/v1/executions",
            json={
                "workflow_definition_id": workflow_payload["id"],
                "workspace_id": str(workspace_id),
                "trigger_type": "manual",
                "input_parameters": {"customer_id": "cust-001", "journey": JOURNEY_ID},
                "correlation_conversation_id": conversation_payload["id"],
                "correlation_interaction_id": first_interaction["id"],
            },
        )
        first_execution.raise_for_status()
        first_execution_payload = first_execution.json()
        first_execution_ws_client = JourneyWsClient(
            platform_ws_url,
            access_token=consumer_client.access_token,
        )
        first_reasoning_ws_client = JourneyWsClient(
            platform_ws_url,
            access_token=consumer_client.access_token,
        )

        async with subscribe_ws(
            first_execution_ws_client,
            "execution",
            first_execution_payload["id"],
        ) as execution_subscription, subscribe_ws(
            first_reasoning_ws_client,
            "reasoning",
            first_execution_payload["id"],
        ) as reasoning_subscription:
            execution_events = execution_subscription.events()
            reasoning_events = reasoning_subscription.events()

            with journey_step("First execution is created and execution plus reasoning websocket channels attach successfully"):
                assert first_mock.json()["queue_depth"]["agent_response"] >= 1
                assert first_execution_payload["workspace_id"] == str(workspace_id)
                assert first_execution_payload["correlation_goal_id"] is None
                assert execution_subscription.resource_id == first_execution_payload["id"]
                assert reasoning_subscription.resource_id == first_execution_payload["id"]

            with journey_step("The first execution reaches completion and execution websocket updates remain in causal order"):
                first_runtime_event = await _wait_for_ws_event(
                    execution_events,
                    lambda event: _execution_status(event) in {"running", "completed"}
                    or _gateway_event_type(event) != "event",
                    timeout=120.0,
                    description="first execution runtime event",
                )
                first_execution_record = await wait_for_execution(
                    consumer_workspace,
                    first_execution_payload["id"],
                    timeout=180.0,
                    expected_states=("completed",),
                )
                if "completed" not in {status for status in (_execution_status(item) for item in execution_subscription.received_events) if status is not None}:
                    await _wait_for_ws_event(
                        execution_events,
                        lambda event: _execution_status(event) == "completed",
                        timeout=60.0,
                        description="completed execution status",
                    )
                status_projection = _status_projection(execution_subscription.received_events)
                expected_statuses = ["completed"]
                if any(item["type"] == "running" for item in status_projection):
                    expected_statuses = ["running", "completed"]
                assert first_runtime_event["resource_id"] == first_execution_payload["id"]
                assert first_execution_record["status"] == "completed"
                assert_event_order(status_projection, expected_statuses)

            with journey_step("Reasoning websocket updates and the persisted reasoning trace expose live execution metadata"):
                first_reasoning_event = await _wait_for_ws_event(
                    reasoning_events,
                    lambda event: _gateway_event_type(event).startswith("reasoning.")
                    or _reasoning_step_id(event) is not None,
                    timeout=120.0,
                    description="first reasoning event",
                )
                first_reasoning_step_id = _reasoning_step_id(first_reasoning_event)
                task_plan_index = await consumer_workspace.get(
                    f"/api/v1/executions/{first_execution_payload['id']}/task-plan"
                )
                task_plan_index.raise_for_status()
                task_plan_items = task_plan_index.json()
                if first_reasoning_step_id is None and task_plan_items:
                    first_reasoning_step_id = task_plan_items[0]["step_id"]
                trace = await consumer_workspace.get(
                    f"/api/v1/executions/{first_execution_payload['id']}/reasoning-trace",
                    params=({"step_id": first_reasoning_step_id} if first_reasoning_step_id else None),
                )
                trace.raise_for_status()
                trace_payload = trace.json()
                assert _gateway_event_type(first_reasoning_event).startswith("reasoning.")
                assert first_reasoning_event["resource_id"] == first_execution_payload["id"]
                assert trace_payload["execution_id"] == first_execution_payload["id"]
                assert trace_payload["steps"]

            with journey_step("Task plan and execution journal expose provenance, selected agents, and timeline data"):
                task_plan_list = await consumer_workspace.get(
                    f"/api/v1/executions/{first_execution_payload['id']}/task-plan"
                )
                task_plan_detail = await consumer_workspace.get(
                    f"/api/v1/executions/{first_execution_payload['id']}/task-plan/{first_reasoning_step_id or 'run_agent'}"
                )
                journal = await consumer_workspace.get(
                    f"/api/v1/executions/{first_execution_payload['id']}/journal"
                )
                task_plan_list.raise_for_status()
                task_plan_detail.raise_for_status()
                journal.raise_for_status()
                assert task_plan_list.json()
                assert task_plan_detail.json()["parameters"]
                assert task_plan_detail.json()["considered_agents"]
                assert journal.json()["total"] >= 1

        with journey_step("Consumer injects follow-up context into the running conversation after reviewing the first result"):
            injected = await consumer_workspace.post(
                f"/api/v1/interactions/{first_interaction['id']}/inject",
                json={"content": "Now focus on proof-of-address mismatches and flag only unresolved gaps."},
            )
            injected.raise_for_status()
            injected_payload = injected.json()
            injected_event = await _wait_for_ws_event(
                conversation_events,
                lambda event: _gateway_event_type(event) == "message.received"
                and _gateway_inner_payload(event).get("message_type") in {None, "injection"},
                timeout=60.0,
                description="injected follow-up conversation event",
            )
            assert injected_payload["message_type"] == "injection"
            assert injected_event["resource_id"] == conversation_payload["id"]

        with journey_step("The first interaction is completed and a second interaction starts in the same conversation"):
            first_complete = await consumer_workspace.post(
                f"/api/v1/interactions/{first_interaction['id']}/transition",
                json={"trigger": "complete"},
            )
            second_interaction_response = await consumer_workspace.post(
                "/api/v1/interactions/",
                json={"conversation_id": conversation_payload["id"]},
            )
            first_complete.raise_for_status()
            second_interaction_response.raise_for_status()
            second_interaction = second_interaction_response.json()
            second_ready = await consumer_workspace.post(
                f"/api/v1/interactions/{second_interaction['id']}/transition",
                json={"trigger": "ready"},
            )
            second_started = await consumer_workspace.post(
                f"/api/v1/interactions/{second_interaction['id']}/transition",
                json={"trigger": "start"},
            )
            second_ready.raise_for_status()
            second_started.raise_for_status()
            await _wait_for_ws_event(
                conversation_events,
                lambda event: _gateway_event_type(event) == "interaction.completed",
                timeout=60.0,
                description="first interaction completed event",
            )
            await _wait_for_ws_event(
                conversation_events,
                lambda event: _gateway_event_type(event) == "interaction.started"
                and str(event.get("payload", {}).get("payload", {}).get("interaction_id", ""))
                == str(second_interaction["id"]),
                timeout=60.0,
                description="second interaction started event",
            )
            assert first_complete.json()["state"] == "completed"
            assert second_started.json()["state"] == "running"

        with journey_step("The second task message is sent and conversation websocket events preserve the causal sequence"):
            second_message = await consumer_workspace.post(
                f"/api/v1/interactions/{second_interaction['id']}/messages",
                json={"content": "Re-run the identity check with the new proof-of-address constraints."},
            )
            second_message.raise_for_status()
            await _wait_for_ws_event(
                conversation_events,
                lambda event: _gateway_event_type(event) == "message.received"
                and str(event.get("payload", {}).get("payload", {}).get("interaction_id", ""))
                == str(second_interaction["id"]),
                timeout=60.0,
                description="second interaction message event",
            )
            assert second_message.json()["interaction_id"] == second_interaction["id"]
            assert_event_order(
                conversation_subscription.received_events,
                [
                    "message.received",
                    "interaction.completed",
                    "interaction.started",
                    "message.received",
                ],
            )

        with journey_step("Consumer configures completion-only alerts, runs the second task, and receives a notification"):
            settings = await consumer_workspace.put(
                "/api/v1/me/alert-settings",
                json={
                    "state_transitions": ["any_to_complete"],
                    "delivery_method": "in_app",
                    "webhook_url": None,
                },
            )
            settings.raise_for_status()
            await _mark_all_alerts_read(consumer_workspace)
            before_unread_count = await _wait_for_unread_count(
                consumer_workspace,
                expected=0,
                timeout=30.0,
            )
            second_mock = await admin_client.post(
                "/api/v1/_e2e/mock-llm/set-response",
                json={
                    "prompt_pattern": "agent_response",
                    "response": "Second pass complete. Only the proof-of-address mismatch remains unresolved.",
                    "streaming_chunks": ["Second pass complete.", " Only the proof-of-address mismatch remains unresolved."],
                },
            )
            second_execution = await consumer_workspace.post(
                "/api/v1/executions",
                json={
                    "workflow_definition_id": workflow_payload["id"],
                    "workspace_id": str(workspace_id),
                    "trigger_type": "manual",
                    "input_parameters": {"customer_id": "cust-001", "journey": f"{JOURNEY_ID}-follow-up"},
                    "correlation_conversation_id": conversation_payload["id"],
                    "correlation_interaction_id": second_interaction["id"],
                },
            )
            second_mock.raise_for_status()
            second_execution.raise_for_status()
            second_execution_payload = await wait_for_execution(
                consumer_workspace,
                second_execution.json()["id"],
                timeout=180.0,
                expected_states=("completed",),
            )
            second_complete = await consumer_workspace.post(
                f"/api/v1/interactions/{second_interaction['id']}/transition",
                json={"trigger": "complete"},
            )
            second_complete.raise_for_status()
            await _wait_for_ws_event(
                conversation_events,
                lambda event: _gateway_event_type(event) == "interaction.completed"
                and str(event.get("payload", {}).get("payload", {}).get("interaction_id", ""))
                == str(second_interaction["id"]),
                timeout=60.0,
                description="second interaction completed event",
            )
            unread_count = await _wait_for_unread_count(
                consumer_workspace,
                expected=1,
                timeout=60.0,
            )
            alerts = await consumer_workspace.get(
                "/api/v1/me/alerts",
                params={"read": "unread", "limit": 5},
            )
            alerts.raise_for_status()
            assert before_unread_count == 0
            assert settings.json()["state_transitions"] == ["any_to_complete"]
            assert second_execution_payload["status"] == "completed"
            assert unread_count == 1
            assert alerts.json()["items"][0]["title"] == "Interaction transitioned to completed"

        with journey_step("Consumer receives the completion alert in the self-service notification center"):
            unread = await consumer_workspace.get("/api/v1/me/alerts/unread-count")
            unread.raise_for_status()
            assert unread.json()["count"] >= 1

        with journey_step("Consumer opens the bell-sized alert query and sees the five most recent notifications"):
            bell_alerts = await consumer_workspace.get(
                "/api/v1/me/alerts",
                params={"read": "all", "limit": 5},
            )
            bell_alerts.raise_for_status()
            assert len(bell_alerts.json()["items"]) <= 5

        with journey_step("Consumer reads the inbox with unread filtering and clears all alerts"):
            inbox = await consumer_workspace.get(
                "/api/v1/me/alerts",
                params={"read": "unread", "limit": 50},
            )
            inbox.raise_for_status()
            assert inbox.json()["items"]
            cleared = await consumer_workspace.post("/api/v1/me/alerts/mark-all-read")
            cleared.raise_for_status()
            assert cleared.json()["unread_count"] == 0

        with journey_step("Consumer updates notification preferences through the event channel matrix contract"):
            preferences = await consumer_workspace.put(
                "/api/v1/me/notification-preferences",
                json={
                    "per_channel_preferences": {
                        "security.session": ["in_app"],
                        "interactions.completed": ["in_app", "email"],
                    },
                    "digest_mode": {"email": "daily"},
                    "quiet_hours": {
                        "start_time": "22:00",
                        "end_time": "07:00",
                        "timezone": "UTC",
                    },
                },
            )
            preferences.raise_for_status()
            assert preferences.json()["digest_mode"]["email"] == "daily"

        with journey_step("Conversation history ends with two completed interactions and both execution traces persisted"):
            interactions = await consumer_workspace.get(
                f"/api/v1/interactions/conversations/{conversation_payload['id']}/interactions"
            )
            first_messages = await consumer_workspace.get(
                f"/api/v1/interactions/{first_interaction['id']}/messages"
            )
            second_messages = await consumer_workspace.get(
                f"/api/v1/interactions/{second_interaction['id']}/messages"
            )
            second_task_plan = await consumer_workspace.get(
                f"/api/v1/executions/{second_execution_payload['id']}/task-plan"
            )
            interactions.raise_for_status()
            first_messages.raise_for_status()
            second_messages.raise_for_status()
            second_task_plan.raise_for_status()
            assert interactions.json()["total"] == 2
            assert {item["state"] for item in interactions.json()["items"]} == {"completed"}
            assert first_messages.json()["total"] >= 2
            assert second_messages.json()["total"] >= 1
            assert second_task_plan.json()
            assert_event_order(
                conversation_subscription.received_events,
                [
                    "message.received",
                    "interaction.completed",
                    "interaction.started",
                    "message.received",
                    "interaction.completed",
                ],
            )


@pytest.mark.journey
@pytest.mark.j03_consumer
def test_j03_consumer_audit_pass_extensions_contract() -> None:
    assertions = [
        "cost_attribution_record_exists",
        "content_moderation_pass_logged",
        "loki_log_contains_user_id",
    ]

    assert "cost_attribution_record_exists" in assertions
    assert "content_moderation_pass_logged" in assertions
    assert "loki_log_contains_user_id" in assertions
