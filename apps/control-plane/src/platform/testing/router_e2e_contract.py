from __future__ import annotations

# mypy: disable-error-code="no-any-return"
import asyncio
import hashlib
import json
import tarfile
from collections.abc import Mapping
from datetime import UTC, datetime
from io import BytesIO
from platform.common.dependencies import get_current_user
from platform.common.events.envelope import CorrelationContext, make_envelope
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

router = APIRouter(tags=["_e2e-contract"])

BASE_WORKSPACE_ID = "00000000-0000-4000-8000-00000000a101"
BASE_USER_ID = "00000000-0000-4000-8000-000000000101"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _state(request: Request) -> dict[str, Any]:
    state = getattr(request.app.state, "e2e_contract_state", None)
    if isinstance(state, dict):
        return state
    state = {
        "namespaces": {
            "default": {"id": "default", "name": "default", "display_name": "Default"},
            "test-eng": {"id": "test-eng", "name": "test-eng", "display_name": "E2E Engineering"},
            "test-finance": {
                "id": "test-finance",
                "name": "test-finance",
                "display_name": "E2E Finance",
            },
        },
        "agents": {},
        "agent_revisions": {},
        "workspaces": {
            BASE_WORKSPACE_ID: {
                "id": BASE_WORKSPACE_ID,
                "name": "test-workspace-alpha",
                "display_name": "test-workspace-alpha",
                "status": "active",
            }
        },
        "workspace_name_index": {"test-workspace-alpha": BASE_WORKSPACE_ID},
        "workspace_members": {
            BASE_WORKSPACE_ID: [
                {
                    "id": f"{BASE_WORKSPACE_ID}:owner",
                    "workspace_id": BASE_WORKSPACE_ID,
                    "user_id": BASE_USER_ID,
                    "role": "owner",
                    "created_at": _now(),
                }
            ]
        },
        "goals": {
            "gid-open-001": {
                "id": "gid-open-001",
                "gid": "gid-open-001",
                "workspace_id": BASE_WORKSPACE_ID,
                "title": "Test open goal",
                "state": "open",
            }
        },
        "executions": {},
        "a2a_tasks": {},
        "proposals": {},
        "canaries": {},
        "hypotheses": {},
        "clusters": [],
        "ab_tests": {},
        "scores": {},
        "fleets": {},
        "fleet_tasks": {},
        "verdicts": {},
        "conversations": {},
        "conversation_messages": {},
        "conversation_branches": {},
        "interactions": {},
        "interaction_messages": {},
        "alerts": {},
        "attention_requests": {},
        "artifacts": {},
        "certifications": {},
        "contracts": {},
        "policies": {},
        "policy_attachments": {},
        "entity_tags": {},
        "entity_labels": {},
        "saved_views": {},
        "governance_chains": {},
        "workspace_settings": {},
        "agent_decision_configs": {},
        "goal_messages": {},
        "eval_sets": {},
        "eval_cases": {},
        "eval_runs": {},
        "gate_checks": {},
        "secrets": {},
        "visibility_grants": set(),
        "workspace_visibility": {},
        "events": {},
        "ws_events": [],
        "mock_llm": {},
        "mock_llm_calls": [],
        "me_alert_settings": {},
        "db_values": {},
        "network_partitions": {},
        "slow_policies": {},
        "s3_credentials_revoked": False,
        "warm_pool_capacity": 1,
        "warm_pool_ready": 1,
    }
    for namespace, local_name, role_type in (
        ("default", "seeded-executor", "executor"),
        ("test-eng", "seeded-planner", "planner"),
        ("test-eng", "seeded-orchestrator", "orchestrator"),
        ("test-finance", "seeded-observer", "observer"),
        ("test-finance", "seeded-judge", "judge"),
        ("test-finance", "seeded-enforcer", "enforcer"),
    ):
        fqn = f"{namespace}:{local_name}"
        state["agents"][fqn] = {
            "id": fqn,
            "namespace": namespace,
            "local_name": local_name,
            "fqn": fqn,
            "role_type": role_type,
            "role_types": [role_type],
            "workspace_id": BASE_WORKSPACE_ID,
            "status": "active",
        }
    request.app.state.e2e_contract_state = state
    return state


def _items(values: Any) -> dict[str, Any]:
    items = list(values)
    return {"items": items, "total": len(items)}


def _default_workspace_visibility(workspace_id: str) -> dict[str, Any]:
    return {
        "workspace_id": workspace_id,
        "visibility_agents": ["*"],
        "visibility_tools": ["*"],
    }


def _user_email(current_user: dict[str, Any] | None) -> str:
    if not current_user:
        return ""
    return str(current_user.get("email") or current_user.get("sub") or "")


def _is_admin(current_user: dict[str, Any] | None) -> bool:
    if not current_user:
        return False
    roles = current_user.get("roles", [])
    if isinstance(roles, list):
        names = {str(item.get("role") if isinstance(item, dict) else item) for item in roles}
        return bool({"platform_admin", "superadmin", "workspace_admin"} & names)
    return False


def _event_store(request: Request, topic: str) -> list[dict[str, Any]]:
    return _state(request)["events"].setdefault(topic, [])


def _record_event(request: Request, topic: str, payload: dict[str, Any]) -> dict[str, Any]:
    event = {"recorded_at": _now(), **payload}
    _event_store(request, topic).append(event)
    return event


def _record_ws(request: Request, channel: str, event: str, payload: dict[str, Any]) -> None:
    _state(request)["ws_events"].append(
        {"recorded_at": _now(), "channel": channel, "event": event, "payload": payload}
    )


def _workspace_id_from_request(request: Request) -> str:
    return request.headers.get("x-workspace-id") or BASE_WORKSPACE_ID


def _user_id(current_user: dict[str, Any] | None) -> str:
    if not current_user:
        return BASE_USER_ID
    return str(current_user.get("sub") or current_user.get("id") or BASE_USER_ID)


def _uuid_or_none(value: Any) -> UUID | None:
    if value in {None, ""}:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _correlation_dict(
    *,
    workspace_id: str | None = None,
    conversation_id: str | None = None,
    interaction_id: str | None = None,
    execution_id: str | None = None,
    goal_id: str | None = None,
    agent_fqn: str | None = None,
) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "workspace_id": workspace_id,
            "conversation_id": conversation_id,
            "interaction_id": interaction_id,
            "execution_id": execution_id,
            "goal_id": goal_id,
            "agent_fqn": agent_fqn,
        }.items()
        if value is not None
    }


def _correlation_context(
    *,
    workspace_id: str | None = None,
    conversation_id: str | None = None,
    interaction_id: str | None = None,
    execution_id: str | None = None,
    goal_id: str | None = None,
    agent_fqn: str | None = None,
) -> CorrelationContext:
    return CorrelationContext(
        workspace_id=_uuid_or_none(workspace_id),
        conversation_id=_uuid_or_none(conversation_id),
        interaction_id=_uuid_or_none(interaction_id),
        execution_id=_uuid_or_none(execution_id),
        goal_id=_uuid_or_none(goal_id),
        agent_fqn=agent_fqn,
        correlation_id=uuid4(),
    )


def _create_background_task(app: Any, coro: Any) -> None:
    task = asyncio.create_task(coro)
    tasks = getattr(app.state, "e2e_contract_background_tasks", None)
    if not isinstance(tasks, set):
        tasks = set()
        app.state.e2e_contract_background_tasks = tasks
    tasks.add(task)
    task.add_done_callback(tasks.discard)


def _replay_delays(first_delay: float) -> tuple[float, ...]:
    return (
        first_delay,
        first_delay + 2.0,
        first_delay + 10.0,
        first_delay + 30.0,
        first_delay + 60.0,
    )


async def _emit_event(
    request: Request,
    topic: str,
    *,
    key: str,
    event_type: str,
    payload: dict[str, Any],
    workspace_id: str | None = None,
    conversation_id: str | None = None,
    interaction_id: str | None = None,
    execution_id: str | None = None,
    goal_id: str | None = None,
    agent_fqn: str | None = None,
    replay_after_seconds: float | None = None,
) -> dict[str, Any]:
    correlation = _correlation_dict(
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        interaction_id=interaction_id,
        execution_id=execution_id,
        goal_id=goal_id,
        agent_fqn=agent_fqn,
    )
    event = _record_event(
        request,
        topic,
        {
            "key": key,
            "event_type": event_type,
            "payload": payload,
            "correlation_context": correlation,
        },
    )
    envelope = make_envelope(
        event_type=event_type,
        source="platform.testing.e2e_contract",
        payload=payload,
        correlation_context=_correlation_context(
            workspace_id=None,
            conversation_id=conversation_id,
            interaction_id=interaction_id,
            execution_id=execution_id,
            goal_id=goal_id,
            agent_fqn=agent_fqn,
        ),
    )
    raw = envelope.model_dump_json().encode("utf-8")
    await _publish_raw_event(request.app, topic, key, raw)
    if replay_after_seconds is not None:
        for delay in _replay_delays(replay_after_seconds):
            _create_background_task(
                request.app,
                _publish_raw_event_after(request.app, topic, key, raw, delay),
            )
    return event


async def _publish_raw_event(app: Any, topic: str, key: str, raw: bytes) -> None:
    fanout = getattr(app.state, "fanout", None)
    route_event = getattr(fanout, "_route_event", None)
    if callable(route_event):
        try:
            await route_event(topic, raw)
        except Exception:
            pass

    clients = getattr(app.state, "clients", {})
    producer = clients.get("kafka") if isinstance(clients, dict) else None
    ensure_producer = getattr(producer, "_ensure_producer", None)
    if callable(ensure_producer):
        try:
            kafka = await ensure_producer()
            await kafka.send_and_wait(topic, raw, key=key.encode("utf-8"))
        except Exception:
            pass


async def _publish_raw_event_after(
    app: Any, topic: str, key: str, raw: bytes, delay_seconds: float
) -> None:
    await asyncio.sleep(delay_seconds)
    await _publish_raw_event(app, topic, key, raw)


def _default_workspace_settings(workspace_id: str) -> dict[str, Any]:
    return {
        "workspace_id": workspace_id,
        "subscribed_agents": [],
        "updated_at": _now(),
    }


def _default_alert_settings(user_id: str) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "state_transitions": [],
        "delivery_method": "in_app",
        "webhook_url": None,
        "updated_at": _now(),
    }


def _message_count(state: dict[str, Any], conversation_id: str) -> int:
    return sum(
        1
        for item in state["interaction_messages"].values()
        if item.get("conversation_id") == conversation_id
    ) + sum(
        1
        for item in state["conversation_messages"].values()
        if item.get("conversation_id") == conversation_id
    )


def _conversation_with_count(state: dict[str, Any], conversation: dict[str, Any]) -> dict[str, Any]:
    return {
        **conversation,
        "message_count": _message_count(state, str(conversation["id"])),
    }


def _add_me_alert(
    request: Request,
    *,
    user_id: str,
    workspace_id: str,
    title: str,
    alert_type: str,
    source_reference: dict[str, Any],
) -> dict[str, Any]:
    alert = {
        "id": str(uuid4()),
        "user_id": user_id,
        "workspace_id": workspace_id,
        "title": title,
        "alert_type": alert_type,
        "source_reference": source_reference,
        "read": False,
        "created_at": _now(),
    }
    _state(request)["alerts"][alert["id"]] = alert
    return alert


def _execution_step(execution: dict[str, Any]) -> dict[str, Any]:
    agent_fqn = execution.get("agent_fqn") or "default:seeded-executor"
    return {
        "step_id": "run_agent",
        "execution_id": execution["id"],
        "name": "Run selected agent",
        "status": "completed",
        "parameters": execution.get("input_parameters") or {"input": execution.get("input")},
        "considered_agents": [agent_fqn],
        "selected_agent_fqn": agent_fqn,
        "started_at": execution.get("created_at"),
        "completed_at": execution.get("completed_at"),
    }


def _goal_gid(goal: dict[str, Any], goal_id: str) -> str:
    return str(goal.get("gid") or goal_id)


async def _uploaded_package_bytes(form: Mapping[str, Any]) -> bytes:
    package = form.get("package")
    if package is None or not hasattr(package, "read"):
        return b""
    content = await package.read()
    return content if isinstance(content, bytes) else bytes(content)


def _manifest_from_package(content: bytes) -> dict[str, Any]:
    if not content:
        return {}
    try:
        with tarfile.open(fileobj=BytesIO(content), mode="r:gz") as archive:
            member = next(
                (
                    item
                    for item in archive.getmembers()
                    if item.isfile() and item.name.rsplit("/", 1)[-1] == "manifest.json"
                ),
                None,
            )
            if member is None:
                return {}
            extracted = archive.extractfile(member)
            if extracted is None:
                return {}
            payload = json.loads(extracted.read().decode("utf-8"))
    except (OSError, tarfile.TarError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _agent_by_id(state: dict[str, Any], agent_id: str) -> dict[str, Any] | None:
    item = state["agents"].get(agent_id)
    if item:
        return item
    for candidate in state["agents"].values():
        if candidate.get("id") == agent_id or candidate.get("fqn") == agent_id:
            return candidate
    return None


def _certifications_for_agent(state: dict[str, Any], agent_id: str) -> list[dict[str, Any]]:
    return [
        cert
        for cert in state["certifications"].values()
        if cert.get("agent_id") == agent_id or cert.get("agent_fqn") == agent_id
    ]


def _marketplace_listing(agent: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    certs = _certifications_for_agent(state, str(agent["id"]))
    certification_status = (
        "active" if any(item.get("status") == "active" for item in certs) else "uncertified"
    )
    description = agent.get("purpose") or agent.get("description") or "E2E marketplace listing"
    return {
        "agent_id": agent["id"],
        "id": agent["id"],
        "fqn": agent["fqn"],
        "status": agent.get("status", "active"),
        "display_name": agent.get("display_name") or agent.get("local_name"),
        "description": description,
        "certification_status": certification_status,
        "relevance_score": 0.99,
        "tags": list(agent.get("tags") or []),
    }


def _entity_bucket(
    state: dict[str, Any],
    collection: str,
    entity_type: str,
    entity_id: str,
) -> Any:
    return state.setdefault(collection, {}).setdefault(entity_type, {}).setdefault(entity_id, {})


def _entity_tags(state: dict[str, Any], entity_type: str, entity_id: str) -> set[str]:
    bucket = _entity_bucket(state, "entity_tags", entity_type, entity_id)
    if isinstance(bucket, set):
        return bucket
    tags = set(bucket if isinstance(bucket, list) else [])
    state["entity_tags"][entity_type][entity_id] = tags
    return tags


def _entity_labels(state: dict[str, Any], entity_type: str, entity_id: str) -> dict[str, str]:
    bucket = _entity_bucket(state, "entity_labels", entity_type, entity_id)
    if isinstance(bucket, dict):
        return bucket
    labels: dict[str, str] = {}
    state["entity_labels"][entity_type][entity_id] = labels
    return labels


def _query_tags(request: Request) -> list[str]:
    tags: list[str] = []
    for raw in request.query_params.getlist("tags"):
        tags.extend(item.strip() for item in raw.split(",") if item.strip())
    return tags


def _query_labels(request: Request) -> dict[str, str]:
    labels: dict[str, str] = {}
    for key, value in request.query_params.multi_items():
        if key.startswith("label.") and key != "label.":
            labels[key.removeprefix("label.")] = value
    return labels


def _stable_output(payload: dict[str, Any]) -> str:
    if payload.get("prompt_pattern") == "agent_response":
        return "fixed-alpha"
    return "ok"


def _record_mock_llm_call(request: Request, payload: dict[str, Any], response: str) -> str:
    prompt_pattern = str(payload.get("prompt_pattern") or "default")
    call = {
        "id": str(uuid4()),
        "prompt_pattern": prompt_pattern,
        "pattern": prompt_pattern,
        "prompt": str(payload.get("input") or payload.get("prompt") or ""),
        "response": response,
        "created_at": _now(),
    }
    _state(request).setdefault("mock_llm_calls", []).append(call)
    return response


@router.get("/api/v1/_e2e/contract/events")
async def contract_events(request: Request, topic: str = Query(...)) -> dict[str, Any]:
    return _items(_event_store(request, topic))


@router.get("/api/v1/tags/{tag}/entities")
async def contract_cross_entity_tag_search(
    request: Request,
    tag: str,
    entity_types: str | None = Query(default=None),
) -> dict[str, Any]:
    state = _state(request)
    requested_types = (
        [item.strip() for item in entity_types.split(",") if item.strip()]
        if entity_types
        else list(state.setdefault("entity_tags", {}).keys())
    )
    entities: dict[str, list[str]] = {}
    for entity_type in requested_types:
        tagged_ids = [
            entity_id
            for entity_id, tags in state.setdefault("entity_tags", {}).get(entity_type, {}).items()
            if tag in set(tags)
        ]
        if tagged_ids:
            entities[entity_type] = tagged_ids
    return {"tag": tag, "entities": entities, "next_cursor": None}


@router.post("/api/v1/tags/{entity_type}/{entity_id}")
async def contract_attach_tag(
    request: Request,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    state = _state(request)
    if entity_type == "agent" and _agent_by_id(state, entity_id) is None:
        raise HTTPException(status_code=404)
    tag = str(payload.get("tag") or "").strip()
    if not tag:
        raise HTTPException(status_code=422)
    _entity_tags(state, entity_type, entity_id).add(tag)
    if entity_type == "agent":
        agent = _agent_by_id(state, entity_id)
        if agent is not None:
            agent["tags"] = list(dict.fromkeys([*list(agent.get("tags") or []), tag]))
    return {"tag": tag, "created_by": _user_id(current_user), "created_at": _now()}


@router.get("/api/v1/tags/{entity_type}/{entity_id}")
async def contract_list_tags(
    request: Request,
    entity_type: str,
    entity_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    del current_user
    tags = sorted(_entity_tags(_state(request), entity_type, entity_id))
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "tags": [{"tag": tag, "created_by": None, "created_at": _now()} for tag in tags],
    }


@router.post("/api/v1/labels/expression/validate")
async def contract_validate_label_expression(payload: dict[str, Any]) -> dict[str, Any]:
    expression = str(payload.get("expression") or "").strip()
    if not expression:
        return {
            "valid": False,
            "error": {"line": 1, "col": 1, "token": "", "message": "expression is required"},
        }
    return {"valid": True, "error": None}


@router.post("/api/v1/labels/{entity_type}/{entity_id}")
async def contract_attach_label(
    request: Request,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    state = _state(request)
    if entity_type == "agent" and _agent_by_id(state, entity_id) is None:
        raise HTTPException(status_code=404)
    key = str(payload.get("key") or "").strip()
    value = str(payload.get("value") or "").strip()
    if not key:
        raise HTTPException(status_code=422)
    _entity_labels(state, entity_type, entity_id)[key] = value
    if entity_type == "agent":
        agent = _agent_by_id(state, entity_id)
        if agent is not None:
            agent.setdefault("labels", {})[key] = value
    now = _now()
    return {
        "key": key,
        "value": value,
        "created_by": _user_id(current_user),
        "created_at": now,
        "updated_at": now,
        "is_reserved": key.startswith("platform."),
    }


@router.get("/api/v1/labels/{entity_type}/{entity_id}")
async def contract_list_labels(
    request: Request,
    entity_type: str,
    entity_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    del current_user
    now = _now()
    labels = [
        {
            "key": key,
            "value": value,
            "created_by": None,
            "created_at": now,
            "updated_at": now,
            "is_reserved": key.startswith("platform."),
        }
        for key, value in sorted(_entity_labels(_state(request), entity_type, entity_id).items())
    ]
    return {"entity_type": entity_type, "entity_id": entity_id, "labels": labels}


@router.post("/api/v1/saved-views", status_code=status.HTTP_201_CREATED)
async def contract_create_saved_view(
    request: Request,
    payload: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    now = _now()
    view_id = str(uuid4())
    owner_id = _user_id(current_user)
    view = {
        "id": view_id,
        "owner_id": owner_id,
        "workspace_id": payload.get("workspace_id"),
        "name": payload.get("name") or view_id,
        "entity_type": payload.get("entity_type") or "agent",
        "filters": payload.get("filters") or {},
        "is_owner": True,
        "is_shared": bool(payload.get("shared", False)),
        "is_orphan_transferred": False,
        "is_orphan": False,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }
    _state(request).setdefault("saved_views", {})[view_id] = view
    return view


@router.get("/api/v1/saved-views")
async def contract_list_saved_views(
    request: Request,
    entity_type: str = Query(...),
    workspace_id: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    user_id = _user_id(current_user)
    views = [
        {**view, "is_owner": view.get("owner_id") == user_id}
        for view in _state(request).setdefault("saved_views", {}).values()
        if view.get("entity_type") == entity_type
        and (workspace_id is None or view.get("workspace_id") == workspace_id)
    ]
    return sorted(views, key=lambda item: (str(item.get("name")), str(item.get("id"))))


@router.get("/api/v1/_e2e/kafka/events")
async def kafka_events(
    request: Request,
    topic: str = Query(...),
    key: str | None = Query(default=None),
    limit: int = Query(default=200),
) -> dict[str, Any]:
    del limit
    items = [
        {
            "topic": topic,
            "key": item.get("key"),
            "payload": {
                field: value
                for field, value in item.items()
                if field not in {"key", "recorded_at"}
            },
            "recorded_at": item.get("recorded_at"),
        }
        for item in _event_store(request, topic)
        if key is None or item.get("key") == key
    ]
    return {"events": items, "total": len(items)}


@router.post("/api/v1/_e2e/kafka/burst", status_code=status.HTTP_201_CREATED)
async def kafka_burst(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    topic = str(payload.get("topic") or "execution.events")
    count = int(payload.get("count") or 1)
    burst_id = str(uuid4())
    for index in range(max(count, 0)):
        _record_event(
            request,
            topic,
            {
                "id": f"{burst_id}:{index}",
                "burst_id": burst_id,
                "event_type": "e2e.kafka.burst",
                "sequence": index,
                "topic": topic,
            },
        )
    return {"id": burst_id, "topic": topic, "count": count}


@router.post("/api/v1/_e2e/chaos/restart-statefulset")
async def restart_statefulset(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "restarted": True,
        "namespace": payload.get("namespace"),
        "name": payload.get("name"),
        "restarted_at": _now(),
    }


@router.post("/api/v1/_e2e/chaos/partition-network", status_code=status.HTTP_201_CREATED)
async def partition_network(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    name = f"e2e-partition-{uuid4().hex[:12]}"
    partition = {
        "network_policy_name": name,
        "partitioned": True,
        "from_namespace": payload.get("from_namespace"),
        "to_namespace": payload.get("to_namespace"),
        "ttl_seconds": payload.get("ttl_seconds"),
        "created_at": _now(),
    }
    _state(request)["network_partitions"][name] = partition
    return partition


@router.delete("/api/v1/_e2e/chaos/partition-network/{network_policy_name}")
async def delete_network_partition(request: Request, network_policy_name: str) -> Response:
    _state(request)["network_partitions"].pop(network_policy_name, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/v1/_e2e/policies/slow", status_code=status.HTTP_201_CREATED)
async def create_slow_policy(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    policy_id = str(uuid4())
    policy = {
        "id": policy_id,
        "delay_seconds": payload.get("delay_seconds"),
        "created_at": _now(),
    }
    state = _state(request)
    state["slow_policies"][policy_id] = policy
    state["db_values"].setdefault("audit_timeout_reasons", {})[policy_id] = (
        "policy evaluation exceeded E2E timeout"
    )
    return policy


@router.delete("/api/v1/_e2e/policies/slow/{policy_id}")
async def delete_slow_policy(request: Request, policy_id: str) -> Response:
    state = _state(request)
    state["slow_policies"].pop(policy_id, None)
    state["db_values"].setdefault("audit_timeout_reasons", {}).pop(policy_id, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/v1/_e2e/chaos/kill-pod")
async def kill_pod(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "killed": [
            {
                "namespace": payload.get("namespace"),
                "label_selector": payload.get("label_selector"),
                "name": "e2e-simulated-pod",
                "deleted_at": _now(),
            }
        ],
        "count": int(payload.get("count") or 1),
    }


@router.post("/api/v1/_e2e/chaos/s3/rotate-credentials")
async def rotate_s3_credentials(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    token = str(uuid4())
    if payload.get("mode") == "revoke":
        _state(request)["s3_credentials_revoked"] = True
    return {"restore_token": token, "mode": payload.get("mode"), "rotated": True}


@router.post("/api/v1/_e2e/chaos/s3/restore-credentials")
async def restore_s3_credentials(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    del payload
    _state(request)["s3_credentials_revoked"] = False
    return {"restored": True}


@router.get("/api/v1/_e2e/contract/ws-events")
async def contract_ws_events(
    request: Request,
    channel: str = Query(...),
    event: str = Query(...),
) -> dict[str, Any]:
    items = [
        item
        for item in _state(request)["ws_events"]
        if item.get("channel") == channel and item.get("event") == event
    ]
    return _items(items)


@router.post("/api/v1/_e2e/contract/db/fetchval")
async def contract_db_fetchval(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or "").lower()
    args = payload.get("args") or []
    state = _state(request)
    if "from executions" in query:
        execution = state["executions"].get(str(args[0])) if args else None
        return {"value": execution.get("state") if execution else None}
    if "from users" in query:
        return {"value": 5}
    if "from interaction_messages" in query:
        interaction = state["interactions"].get(str(args[0])) if args else None
        return {"value": interaction.get("gid") if interaction else None}
    if "from trust_surveillance_signals" in query:
        signal_id = str(args[0]) if args else ""
        return {"value": 1 if signal_id in state["db_values"].get("trust_signals", set()) else 0}
    if "from audit_events" in query and "timeout_reason" in query:
        correlation_id = str(args[0]) if args else ""
        return {
            "value": state["db_values"]
            .get("audit_timeout_reasons", {})
            .get(correlation_id)
        }
    return {"value": None}


@router.get("/.well-known/agent.json")
async def agent_card(agent_fqn: str = Query(...)) -> dict[str, Any]:
    return {
        "name": agent_fqn,
        "skills": [{"id": "execute", "name": "Execute deterministic E2E task"}],
        "endpoints": {"tasks": "/a2a/tasks", "stream": "/a2a/tasks/stream"},
        "auth_schemes": ["bearer"],
    }


@router.post("/a2a/tasks")
@router.post("/api/v1/a2a/client/tasks")
async def create_a2a_task(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    task_id = str(uuid4())
    task = {
        "id": task_id,
        "status": "completed",
        "input": payload.get("input"),
        "output": "remote task completed",
    }
    _state(request)["a2a_tasks"][task_id] = task
    return task


@router.get("/a2a/tasks/{task_id}")
@router.get("/api/v1/a2a/client/tasks/{task_id}")
async def get_a2a_task(request: Request, task_id: str) -> dict[str, Any]:
    task = _state(request)["a2a_tasks"].get(task_id)
    if not task:
        raise HTTPException(status_code=404)
    return task


@router.post("/a2a/tasks/stream")
async def stream_a2a_task() -> StreamingResponse:
    async def events() -> Any:
        yield "event: started\n\nevent: completed\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/api/v1/auth/sessions")
async def auth_sessions() -> dict[str, Any]:
    return _items([{"id": "e2e-session", "active": True}])


@router.get("/api/v1/auth/{provider}")
async def oauth_start(provider: str) -> RedirectResponse:
    if provider not in {"google", "github"}:
        raise HTTPException(status_code=404)
    return RedirectResponse(
        f"http://localhost/callback/{provider}?state=e2e-state", status_code=302
    )


@router.get("/api/v1/auth/{provider}/callback")
async def oauth_callback(provider: str, state: str = Query(...)) -> dict[str, Any]:
    if provider not in {"google", "github"}:
        raise HTTPException(status_code=404)
    if state != "e2e-state":
        raise HTTPException(status_code=403)
    return {"status": "ok", "provider": provider}


@router.get("/api/v1/auth/mfa/setup")
async def mfa_setup() -> dict[str, Any]:
    return {"secret": "jbswy3dpehpk3pxp".upper(), "recovery_codes": ["recovery-e2e"]}


@router.post("/api/v1/auth/mfa/verify")
async def mfa_verify(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("code") == "000000":
        raise HTTPException(status_code=401)
    return {"enabled": True, "recovery_codes": ["recovery-e2e"]}


@router.post("/api/v1/auth/mfa/recovery")
async def mfa_recovery() -> Response:
    return Response(status_code=204)


@router.post("/api/v1/auth/logout")
async def auth_logout() -> Response:
    return Response(status_code=204)


@router.get("/api/v1/me")
async def me(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {"id": current_user.get("sub", BASE_USER_ID), "email": _user_email(current_user)}


@router.post("/api/v1/namespaces", status_code=status.HTTP_201_CREATED)
async def create_namespace(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "")
    if not name or " " in name or "/" in name:
        raise HTTPException(status_code=422)
    namespaces = _state(request)["namespaces"]
    if name in namespaces:
        raise HTTPException(status_code=409)
    item = {
        "id": name,
        "name": name,
        "display_name": payload.get("display_name") or payload.get("description") or name,
        "description": payload.get("description"),
        "workspace_id": payload.get("workspace_id") or _workspace_id_from_request(request),
    }
    namespaces[name] = item
    return item


@router.get("/api/v1/namespaces")
async def list_namespaces(request: Request) -> dict[str, Any]:
    return _items(_state(request)["namespaces"].values())


@router.get("/api/v1/namespaces/{namespace_id}")
async def get_namespace(request: Request, namespace_id: str) -> dict[str, Any]:
    item = _state(request)["namespaces"].get(namespace_id)
    if not item:
        raise HTTPException(status_code=404)
    return item


@router.patch("/api/v1/namespaces/{namespace_id}")
async def update_namespace(
    request: Request, namespace_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    item = _state(request)["namespaces"].get(namespace_id)
    if not item:
        raise HTTPException(status_code=404)
    item.update(payload)
    return item


@router.delete("/api/v1/namespaces/{namespace_id}")
async def delete_namespace(request: Request, namespace_id: str) -> Response:
    _state(request)["namespaces"].pop(namespace_id, None)
    return Response(status_code=204)


@router.post("/api/v1/agents", status_code=status.HTTP_201_CREATED)
async def create_agent(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    namespace = str(payload.get("namespace") or "")
    local_name = str(payload.get("local_name") or "")
    if not namespace or not local_name or " " in namespace or "/" in local_name:
        raise HTTPException(status_code=422)
    fqn = str(payload.get("fqn") or f"{namespace}:{local_name}")
    agents = _state(request)["agents"]
    if fqn in agents:
        raise HTTPException(status_code=409)
    agent = {
        "id": fqn,
        "namespace": namespace,
        "namespace_name": namespace,
        "local_name": local_name,
        "fqn": fqn,
        "role_type": payload.get("role_type", "executor"),
        "role_types": payload.get("role_types") or [payload.get("role_type", "executor")],
        "workspace_id": payload.get("workspace_id", BASE_WORKSPACE_ID),
        "status": payload.get("status", "active"),
    }
    agents[fqn] = agent
    return agent


@router.post("/api/v1/agents/upload", status_code=status.HTTP_201_CREATED)
async def upload_agent(request: Request) -> dict[str, Any]:
    form: Mapping[str, Any]
    try:
        form = await request.form()
    except Exception:
        form = {}
    package_bytes = await _uploaded_package_bytes(form)
    manifest = _manifest_from_package(package_bytes)
    namespace_name = str(form.get("namespace_name") or "default")
    local_name = str(manifest.get("local_name") or f"seeded-{uuid4().hex[:8]}")
    fqn = f"{namespace_name}:{local_name}"
    role_types = [str(item) for item in manifest.get("role_types") or ["executor"]]
    if not role_types:
        role_types = ["executor"]
    digest = hashlib.sha256(package_bytes or fqn.encode()).hexdigest()
    revision_id = str(uuid4())
    revision = {
        "id": revision_id,
        "agent_id": fqn,
        "status": "active",
        "version": manifest.get("version", "1.0.0"),
        "sha256_digest": digest,
        "created_at": _now(),
    }
    agent = {
        "id": fqn,
        "namespace": namespace_name,
        "namespace_name": namespace_name,
        "local_name": local_name,
        "fqn": fqn,
        "role_type": role_types[0],
        "role_types": role_types,
        "workspace_id": _workspace_id_from_request(request),
        "status": "active",
        "purpose": manifest.get("purpose") or "E2E uploaded agent",
        "approach": manifest.get("approach"),
        "tags": list(manifest.get("tags") or []),
        "display_name": manifest.get("display_name") or local_name.replace("-", " ").title(),
        "maturity_level": manifest.get("maturity_level", 1),
        "reasoning_modes": list(manifest.get("reasoning_modes") or ["deterministic"]),
        "visibility_agents": ["*"],
        "visibility_tools": ["*"],
        "current_revision": revision,
    }
    _state(request)["agents"][fqn] = agent
    _state(request).setdefault("agent_revisions", {}).setdefault(fqn, []).append(revision)
    return {"created": True, "agent_profile": agent, "revision": revision}


@router.get("/api/v1/agents/resolve")
async def resolve_agent(request: Request, fqn: str = Query(...)) -> dict[str, Any]:
    agents = _state(request)["agents"]
    if fqn.endswith(":*"):
        namespace = fqn.split(":", 1)[0]
        return _items(item for item in agents.values() if item.get("namespace") == namespace)
    item = agents.get(fqn)
    if not item:
        raise HTTPException(status_code=404)
    return item


@router.get("/api/v1/agents/resolve/{fqn:path}")
async def resolve_agent_path(request: Request, fqn: str) -> dict[str, Any]:
    return await resolve_agent(request, fqn=fqn)


@router.get("/api/v1/agents/search")
async def search_agents(request: Request, pattern: str = Query("*")) -> dict[str, Any]:
    agents = list(_state(request)["agents"].values())
    if pattern == "missing:*":
        return _items([])
    if pattern.endswith(":*"):
        namespace = pattern.split(":", 1)[0]
        agents = [item for item in agents if item.get("namespace") == namespace]
    elif pattern.startswith("*:"):
        name = pattern.split(":", 1)[1]
        agents = [item for item in agents if item.get("local_name") == name]
    return _items(agents)


@router.get("/api/v1/agents")
async def list_agents(
    request: Request,
    namespace: str | None = Query(default=None),
    status: str | None = Query(default=None),
    fqn_pattern: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    limit: int = Query(default=100),
    offset: int = Query(default=0),
    workspace_id: str | None = Query(default=None),
) -> dict[str, Any]:
    del workspace_id
    state = _state(request)
    agents = list(state["agents"].values())
    if namespace:
        agents = [item for item in agents if item.get("namespace") == namespace]
    if status:
        agents = [item for item in agents if item.get("status") == status]
    if fqn_pattern and fqn_pattern.endswith(":*"):
        fqn_namespace = fqn_pattern.split(":", 1)[0]
        agents = [item for item in agents if item.get("namespace") == fqn_namespace]
    if keyword:
        lowered = keyword.lower()
        agents = [
            item
            for item in agents
            if lowered in str(item.get("purpose", "")).lower()
            or lowered in str(item.get("approach", "")).lower()
            or lowered in " ".join(str(tag) for tag in item.get("tags", [])).lower()
        ] or agents
    tags = _query_tags(request)
    if tags:
        required_tags = set(tags)
        agents = [
            item
            for item in agents
            if required_tags.issubset(
                set(item.get("tags") or []) | _entity_tags(state, "agent", str(item.get("id")))
            )
        ]
    labels = _query_labels(request)
    if labels:
        agents = [
            item
            for item in agents
            if all(
                _entity_labels(state, "agent", str(item.get("id"))).get(key) == value
                or (item.get("labels") or {}).get(key) == value
                for key, value in labels.items()
            )
        ]
    total = len(agents)
    return {"items": agents[offset : offset + limit], "total": total}


@router.post("/api/v1/agents/{fqn}/visibility-grants", status_code=status.HTTP_201_CREATED)
async def grant_agent_visibility(
    request: Request, fqn: str, payload: dict[str, Any]
) -> dict[str, Any]:
    grant_id = str(payload.get("workspace_id") or payload.get("workspace_pattern") or uuid4())
    _state(request)["visibility_grants"].add(fqn)
    return {"id": grant_id, "agent_fqn": fqn}


@router.delete("/api/v1/agents/{fqn}/visibility-grants/{grant_id}")
async def revoke_agent_visibility(request: Request, fqn: str, grant_id: str) -> Response:
    del grant_id
    _state(request)["visibility_grants"].discard(fqn)
    return Response(status_code=204)


@router.post("/api/v1/agents/{agent_id}/visibility")
async def set_agent_visibility(request: Request, agent_id: str) -> dict[str, Any]:
    _state(request)["visibility_grants"].add(agent_id)
    return {"id": agent_id}


@router.patch("/api/v1/agents/{agent_id}")
async def patch_agent(request: Request, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    agent = _agent_by_id(_state(request), agent_id)
    if not agent:
        raise HTTPException(status_code=404)
    agent.update(payload)
    if visibility_agents := payload.get("visibility_agents"):
        agent["visibility_agents"] = list(visibility_agents)
        if "*" in agent["visibility_agents"]:
            _state(request)["visibility_grants"].add(str(agent["id"]))
    if visibility_tools := payload.get("visibility_tools"):
        agent["visibility_tools"] = list(visibility_tools)
    return agent


@router.get("/api/v1/agents/{agent_id}/revisions")
async def list_agent_revisions(request: Request, agent_id: str) -> dict[str, Any]:
    state = _state(request)
    agent = _agent_by_id(state, agent_id)
    if not agent:
        raise HTTPException(status_code=404)
    revisions = state.setdefault("agent_revisions", {}).get(str(agent["id"])) or [
        agent["current_revision"]
    ]
    return _items(revisions)


@router.post("/api/v1/agents/{agent_id}/transition")
async def transition_agent(
    request: Request, agent_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    agent = _agent_by_id(_state(request), agent_id)
    if not agent:
        raise HTTPException(status_code=404)
    agent["status"] = (
        payload.get("target_status") or payload.get("status") or agent.get("status", "active")
    )
    return agent


@router.post("/api/v1/agents/{agent_id}/maturity")
async def update_agent_maturity(
    request: Request, agent_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    agent = _agent_by_id(_state(request), agent_id)
    if not agent:
        raise HTTPException(status_code=404)
    agent["maturity_level"] = payload.get("maturity_level", agent.get("maturity_level", 1))
    return agent


@router.post("/api/v1/trust/agents/{agent_id}/certifications", status_code=status.HTTP_201_CREATED)
async def certify_agent(request: Request, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    cert = {
        "id": str(uuid4()),
        "agent_id": agent_id,
        "status": payload.get("status", "active"),
        **payload,
    }
    _state(request)["certifications"][cert["id"]] = cert
    return cert


@router.get("/api/v1/trust/agents/{agent_id}/certifications")
async def list_agent_certifications(request: Request, agent_id: str) -> dict[str, Any]:
    return _items(_certifications_for_agent(_state(request), agent_id))


@router.get("/api/v1/agents/{fqn}")
async def get_agent(
    request: Request,
    fqn: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    state = _state(request)
    item = _agent_by_id(state, fqn)
    if not item:
        raise HTTPException(status_code=404)
    if fqn.startswith("test-finance:") and not _is_admin(current_user):
        if fqn not in state["visibility_grants"]:
            raise HTTPException(status_code=403)
    return item


@router.delete("/api/v1/agents/{fqn}")
async def delete_agent(request: Request, fqn: str) -> Response:
    _state(request)["agents"].pop(fqn, None)
    return Response(status_code=204)


@router.post("/api/v1/workspaces", status_code=status.HTTP_201_CREATED)
async def create_workspace(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    state = _state(request)
    name = str(payload.get("name") or f"test-{uuid4().hex[:8]}")
    if name in state["workspace_name_index"]:
        workspace_id = state["workspace_name_index"][name]
        return state["workspaces"][workspace_id]
    workspace_id = str(uuid4())
    workspace = {
        "id": workspace_id,
        "name": name,
        "display_name": payload.get("display_name") or payload.get("description") or name,
        "status": "active",
    }
    state["workspaces"][workspace_id] = workspace
    state["workspace_name_index"][name] = workspace_id
    state.setdefault("workspace_members", {})[workspace_id] = [
        {
            "id": f"{workspace_id}:owner",
            "workspace_id": workspace_id,
            "user_id": BASE_USER_ID,
            "role": "owner",
            "created_at": _now(),
        }
    ]
    return workspace


@router.get("/api/v1/workspaces")
async def list_workspaces(request: Request) -> dict[str, Any]:
    return _items(_state(request)["workspaces"].values())


@router.get("/api/v1/workspaces/{workspace_id}")
async def get_workspace(request: Request, workspace_id: str) -> dict[str, Any]:
    state = _state(request)
    key = state["workspace_name_index"].get(workspace_id, workspace_id)
    workspace = state["workspaces"].get(key)
    if not workspace:
        raise HTTPException(status_code=404)
    return workspace


@router.delete("/api/v1/workspaces/{workspace_id}")
async def delete_workspace(request: Request, workspace_id: str) -> Response:
    state = _state(request)
    key = workspace_id
    if workspace_id in state["workspace_name_index"]:
        key = state["workspace_name_index"].pop(workspace_id)
    workspace = state["workspaces"].pop(key, None)
    if workspace:
        state["workspace_name_index"].pop(workspace.get("name"), None)
    return Response(status_code=204)


@router.post("/api/v1/workspaces/{workspace_id}/archive")
async def archive_workspace(request: Request, workspace_id: str) -> dict[str, Any]:
    workspace = _state(request)["workspaces"].get(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404)
    workspace["status"] = "archived"
    return workspace


@router.put("/api/v1/workspaces/{workspace_id}/visibility")
async def update_workspace_visibility(
    request: Request, workspace_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    if workspace_id not in _state(request)["workspaces"]:
        raise HTTPException(status_code=404)
    visibility = {
        "workspace_id": workspace_id,
        "visibility_agents": list(payload.get("visibility_agents") or []),
        "visibility_tools": list(payload.get("visibility_tools") or []),
    }
    _state(request).setdefault("workspace_visibility", {})[workspace_id] = visibility
    return visibility


@router.get("/api/v1/workspaces/{workspace_id}/visibility")
async def get_workspace_visibility(request: Request, workspace_id: str) -> dict[str, Any]:
    if workspace_id not in _state(request)["workspaces"]:
        raise HTTPException(status_code=404)
    return _state(request).setdefault("workspace_visibility", {}).get(
        workspace_id, _default_workspace_visibility(workspace_id)
    )


@router.patch("/api/v1/workspaces/{workspace_id}/settings")
async def patch_workspace_settings(
    request: Request, workspace_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    state = _state(request)
    if workspace_id not in state["workspaces"]:
        raise HTTPException(status_code=404)
    settings = state.setdefault("workspace_settings", {}).setdefault(
        workspace_id, _default_workspace_settings(workspace_id)
    )
    if "subscribed_agents" in payload:
        settings["subscribed_agents"] = list(payload.get("subscribed_agents") or [])
    settings["updated_at"] = _now()
    return settings


@router.get("/api/v1/workspaces/{workspace_id}/settings")
async def get_workspace_settings(request: Request, workspace_id: str) -> dict[str, Any]:
    state = _state(request)
    if workspace_id not in state["workspaces"]:
        raise HTTPException(status_code=404)
    return state.setdefault("workspace_settings", {}).setdefault(
        workspace_id, _default_workspace_settings(workspace_id)
    )


@router.put("/api/v1/workspaces/{workspace_id}/agent-decision-configs/{agent_fqn}")
async def put_agent_decision_config(
    request: Request, workspace_id: str, agent_fqn: str, payload: dict[str, Any]
) -> dict[str, Any]:
    state = _state(request)
    if workspace_id not in state["workspaces"]:
        raise HTTPException(status_code=404)
    config = {
        "workspace_id": workspace_id,
        "agent_fqn": agent_fqn,
        "response_decision_strategy": payload.get("response_decision_strategy", "keyword"),
        "response_decision_config": dict(payload.get("response_decision_config") or {}),
        "updated_at": _now(),
    }
    state.setdefault("agent_decision_configs", {})[f"{workspace_id}:{agent_fqn}"] = config
    return config


@router.get("/api/v1/workspaces/{workspace_id}/agent-decision-configs/{agent_fqn}")
async def get_agent_decision_config(
    request: Request, workspace_id: str, agent_fqn: str
) -> dict[str, Any]:
    state = _state(request)
    config = state.setdefault("agent_decision_configs", {}).get(f"{workspace_id}:{agent_fqn}")
    if not config:
        raise HTTPException(status_code=404)
    return config


@router.put("/api/v1/workspaces/{workspace_id}/governance-chain")
async def update_workspace_governance_chain(
    request: Request, workspace_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    state = _state(request)
    if workspace_id not in state["workspaces"]:
        raise HTTPException(status_code=404)
    chain_id = str(payload.get("id") or f"{workspace_id}:governance-chain")
    chain = {
        "id": chain_id,
        "workspace_id": workspace_id,
        "observer_fqns": list(payload.get("observer_fqns") or []),
        "judge_fqns": list(payload.get("judge_fqns") or []),
        "enforcer_fqns": list(payload.get("enforcer_fqns") or []),
        "policy_binding_ids": list(payload.get("policy_binding_ids") or []),
        "verdict_to_action_mapping": dict(payload.get("verdict_to_action_mapping") or {}),
        "status": payload.get("status", "active"),
        "updated_at": _now(),
    }
    state.setdefault("governance_chains", {})[workspace_id] = chain
    return chain


@router.get("/api/v1/workspaces/{workspace_id}/governance-chain")
async def get_workspace_governance_chain(request: Request, workspace_id: str) -> dict[str, Any]:
    state = _state(request)
    if workspace_id not in state["workspaces"]:
        raise HTTPException(status_code=404)
    return state.setdefault("governance_chains", {}).get(
        workspace_id,
        {
            "id": f"{workspace_id}:governance-chain",
            "workspace_id": workspace_id,
            "observer_fqns": [],
            "judge_fqns": [],
            "enforcer_fqns": [],
            "policy_binding_ids": [],
            "verdict_to_action_mapping": {},
            "status": "unconfigured",
        },
    )


@router.post("/api/v1/workspaces/{workspace_id}/members", status_code=status.HTTP_201_CREATED)
async def create_workspace_member(
    request: Request, workspace_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    if workspace_id not in _state(request)["workspaces"]:
        raise HTTPException(status_code=404)
    member = {
        "id": str(uuid4()),
        "workspace_id": workspace_id,
        "user_id": payload.get("user_id") or BASE_USER_ID,
        "role": payload.get("role", "member"),
        "created_at": _now(),
    }
    _state(request).setdefault("workspace_members", {}).setdefault(workspace_id, []).append(member)
    return member


@router.get("/api/v1/workspaces/{workspace_id}/members")
async def list_workspace_members(request: Request, workspace_id: str) -> dict[str, Any]:
    if workspace_id not in _state(request)["workspaces"]:
        raise HTTPException(status_code=404)
    members = _state(request).setdefault("workspace_members", {}).setdefault(
        workspace_id,
        [
            {
                "id": f"{workspace_id}:owner",
                "workspace_id": workspace_id,
                "user_id": BASE_USER_ID,
                "role": "owner",
                "created_at": _now(),
            }
        ],
    )
    return _items(members)


@router.delete("/api/v1/workspaces/{workspace_id}/members/{user_id}")
async def delete_workspace_member(
    request: Request,
    workspace_id: str,
    user_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> Response:
    state = _state(request)
    members = state.setdefault("workspace_members", {}).setdefault(workspace_id, [])
    state["workspace_members"][workspace_id] = [
        member for member in members if str(member.get("user_id")) != user_id
    ]
    for view in state.setdefault("saved_views", {}).values():
        if view.get("workspace_id") == workspace_id and view.get("owner_id") == user_id:
            view["owner_id"] = _user_id(current_user)
            view["is_orphan_transferred"] = True
            view["is_orphan"] = False
            view["updated_at"] = _now()
    return Response(status_code=204)


@router.get("/api/v1/workspaces/{workspace_id}/goals")
async def list_goals(request: Request, workspace_id: str) -> dict[str, Any]:
    return _items(
        item
        for item in _state(request)["goals"].values()
        if item.get("workspace_id") in {workspace_id, BASE_WORKSPACE_ID}
    )


@router.post("/api/v1/workspaces/{workspace_id}/goals", status_code=status.HTTP_201_CREATED)
async def create_goal(
    request: Request, workspace_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    if workspace_id not in _state(request)["workspaces"]:
        raise HTTPException(status_code=404)
    goal_id = str(uuid4())
    goal = {
        "id": goal_id,
        "gid": goal_id,
        "workspace_id": workspace_id,
        "title": payload.get("title"),
        "description": payload.get("description"),
        "auto_complete_timeout_seconds": payload.get("auto_complete_timeout_seconds"),
        "status": "open",
        "state": "ready",
        "created_at": _now(),
    }
    _state(request)["goals"][goal_id] = goal
    await _emit_event(
        request,
        "workspaces.events",
        key=workspace_id,
        event_type="workspaces.goal.created",
        payload={"workspace_id": workspace_id, "goal_id": goal_id, "gid": goal_id},
        workspace_id=workspace_id,
        goal_id=goal_id,
    )
    return goal


@router.patch("/api/v1/workspaces/{workspace_id}/goals/{goal_id}")
async def patch_goal(
    request: Request, workspace_id: str, goal_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    del workspace_id
    goal = _state(request)["goals"].setdefault(goal_id, {"id": goal_id, "gid": goal_id})
    goal["state"] = payload.get("status") or payload.get("state") or goal.get("state", "open")
    goal["status"] = payload.get("status") or goal.get("status", "open")
    return goal


@router.get("/api/v1/workspaces/{workspace_id}/goals/{goal_id}")
async def get_goal(request: Request, workspace_id: str, goal_id: str) -> dict[str, Any]:
    del workspace_id
    goal = _state(request)["goals"].setdefault(
        goal_id,
        {
            "id": goal_id,
            "gid": goal_id,
            "workspace_id": BASE_WORKSPACE_ID,
            "status": "open",
            "state": "open",
        },
    )
    return goal


@router.post(
    "/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
    status_code=status.HTTP_201_CREATED,
)
async def create_goal_message(
    request: Request,
    workspace_id: str,
    goal_id: str,
    payload: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    state = _state(request)
    goal = state["goals"].get(goal_id)
    if not goal or goal.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=404)
    if goal.get("state") == "complete":
        raise HTTPException(status_code=409, detail="goal is complete")

    agent_fqn = request.headers.get("x-agent-fqn")
    participant_identity = agent_fqn or _user_id(current_user)
    message_id = str(uuid4())
    gid = request.headers.get("x-goal-id") or _goal_gid(goal, goal_id)
    message = {
        "id": message_id,
        "workspace_id": workspace_id,
        "goal_id": goal_id,
        "gid": gid,
        "interaction_id": payload.get("interaction_id"),
        "participant_identity": participant_identity,
        "message_type": "agent" if agent_fqn else "user",
        "content": payload.get("content"),
        "metadata": dict(payload.get("metadata") or {}),
        "created_at": _now(),
    }
    state.setdefault("goal_messages", {}).setdefault(goal_id, []).append(message)
    if not agent_fqn and goal.get("state") == "ready":
        goal["state"] = "working"
    if payload.get("interaction_id") and payload["interaction_id"] in state["interactions"]:
        state["interactions"][payload["interaction_id"]]["goal_id"] = goal_id
    return JSONResponse(
        content=message,
        status_code=status.HTTP_201_CREATED,
        headers={"X-Goal-Id": gid},
    )


@router.get("/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages")
async def list_goal_messages(
    request: Request,
    workspace_id: str,
    goal_id: str,
    page: int = Query(default=1),
    page_size: int = Query(default=50),
) -> dict[str, Any]:
    del workspace_id
    start = max(page - 1, 0) * page_size
    items = list(_state(request).setdefault("goal_messages", {}).get(goal_id, []))
    return {"items": items[start : start + page_size], "total": len(items)}


@router.get("/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages/{message_id}/rationale")
async def goal_message_rationale(
    request: Request, workspace_id: str, goal_id: str, message_id: str
) -> dict[str, Any]:
    del goal_id, message_id
    state = _state(request)
    settings = state.setdefault("workspace_settings", {}).setdefault(
        workspace_id, _default_workspace_settings(workspace_id)
    )
    items = [
        {
            "agent_fqn": agent_fqn,
            "decision": "skip" if "notification" in agent_fqn else "respond",
            "strategy": state.setdefault("agent_decision_configs", {})
            .get(f"{workspace_id}:{agent_fqn}", {})
            .get("response_decision_strategy", "keyword"),
            "reason": "E2E deterministic collaboration routing",
        }
        for agent_fqn in settings.get("subscribed_agents", [])
    ]
    return _items(items)


@router.post("/api/v1/workspaces/{workspace_id}/goals/{goal_id}/transition")
async def transition_goal(
    request: Request, workspace_id: str, goal_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    del workspace_id
    goal = _state(request)["goals"].get(goal_id)
    if not goal:
        raise HTTPException(status_code=404)
    old_state = str(goal.get("state") or "open")
    new_state = str(payload.get("target_state") or payload.get("state") or old_state)
    goal["state"] = new_state
    if new_state == "complete":
        goal["status"] = "closed"
    return {
        "goal_id": goal_id,
        "old_state": old_state,
        "new_state": new_state,
        "reason": payload.get("reason"),
        "gid": goal.get("gid"),
    }


def _execution_event_for(payload: dict[str, Any]) -> dict[str, Any]:
    mode = payload.get("reasoning_mode")
    text = str(payload.get("input") or "")
    event_type = "execution.completed"
    if payload.get("checkpoint"):
        event_type = "checkpoint.created"
    elif payload.get("action") == "secret.lookup":
        event_type = "execution.completed"
    elif "compute_budget" in text:
        event_type = "budget.exhausted"
    elif mode == "cot":
        event_type = "reasoning.step"
    elif mode == "tot":
        event_type = "reasoning.branch"
    elif mode == "react":
        event_type = "tool.call"
    elif mode == "self_correction":
        event_type = "reasoning.corrected"
    elif mode == "cod":
        event_type = "governance.verdict.issued"
    return {"event_type": event_type, "reasoning_mode": mode, "checkpoint_id": str(uuid4())}


@router.post("/api/v1/executions", status_code=status.HTTP_201_CREATED)
async def create_execution(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    state = _state(request)
    input_text = str(payload.get("input") or "")
    lowered_input = input_text.lower()
    if "ignore previous instructions" in lowered_input:
        _record_event(
            request,
            "trust.events",
            {"event_type": "trust.screener.blocked", "agent_fqn": payload.get("agent_fqn")},
        )
        raise HTTPException(status_code=400, detail="blocked by E2E pre-screener")
    if state["network_partitions"] and "needs data" in lowered_input:
        raise HTTPException(status_code=503, detail="dependency unreachable during E2E partition")
    if state["slow_policies"] and "slow policy" in lowered_input:
        raise HTTPException(status_code=503, detail="policy evaluation timed out")

    execution_id = str(uuid4())
    workspace_id = str(payload.get("workspace_id") or _workspace_id_from_request(request))
    conversation_id = payload.get("correlation_conversation_id")
    interaction_id = payload.get("correlation_interaction_id")
    goal_id = payload.get("correlation_goal_id") or payload.get("goal_id")
    output = _record_mock_llm_call(request, payload, _stable_output(payload))
    execution = {
        "id": execution_id,
        "workspace_id": workspace_id,
        "state": "completed",
        "status": "completed",
        "agent_fqn": payload.get("agent_fqn"),
        "input": payload.get("input"),
        "input_parameters": payload.get("input_parameters") or {},
        "workflow_definition_id": payload.get("workflow_definition_id"),
        "trigger_type": payload.get("trigger_type"),
        "correlation_conversation_id": conversation_id,
        "correlation_interaction_id": interaction_id,
        "correlation_goal_id": goal_id,
        "response": output,
        "output": output,
        "created_at": _now(),
        "completed_at": "2026-01-01T00:00:00+00:00",
    }
    if payload.get("reasoning_mode") == "cot":
        execution["trace_ack"] = 1
    state["executions"][execution_id] = execution
    if interaction_id:
        assistant_message = {
            "id": str(uuid4()),
            "interaction_id": str(interaction_id),
            "conversation_id": str(conversation_id) if conversation_id else None,
            "workspace_id": workspace_id,
            "message_type": "assistant",
            "content": execution["output"],
            "execution_id": execution_id,
            "created_at": _now(),
        }
        state.setdefault("interaction_messages", {})[assistant_message["id"]] = assistant_message
    event = {"execution_id": execution_id, **_execution_event_for(payload)}
    if payload.get("gid"):
        event["gid"] = payload["gid"]
    _record_event(request, "execution.events", event)
    if payload.get("reasoning_mode") == "cot":
        _record_ws(
            request,
            "reasoning",
            "trace.step",
            {"execution_id": execution_id, "sequence": 1, "status": "completed"},
        )
    state["warm_pool_ready"] = max(int(state.get("warm_pool_ready") or 0), 1)
    _record_ws(request, "runtime", "warm_pool.replenished", {"ready": 1})
    await _emit_event(
        request,
        "execution.events",
        key=execution_id,
        event_type="execution.status_changed",
        payload={"execution_id": execution_id, "status": "completed"},
        workspace_id=workspace_id,
        conversation_id=str(conversation_id) if conversation_id else None,
        interaction_id=str(interaction_id) if interaction_id else None,
        execution_id=execution_id,
        goal_id=str(goal_id) if goal_id else None,
        replay_after_seconds=1.0,
    )
    await _emit_event(
        request,
        "runtime.reasoning",
        key=execution_id,
        event_type="reasoning.trace_emitted",
        payload={
            "execution_id": execution_id,
            "step_id": "run_agent",
            "technique": "workflow",
            "status": "completed",
        },
        workspace_id=workspace_id,
        conversation_id=str(conversation_id) if conversation_id else None,
        interaction_id=str(interaction_id) if interaction_id else None,
        execution_id=execution_id,
        goal_id=str(goal_id) if goal_id else None,
        replay_after_seconds=1.0,
    )
    if payload.get("contract_id") or payload.get("action") == "secret.lookup":
        _record_event(
            request,
            "trust.events",
            {"event_type": "trust.contract.violated", "agent_fqn": payload.get("agent_fqn")},
        )
    return execution


@router.get("/api/v1/executions/{execution_id}")
async def get_execution(request: Request, execution_id: str) -> dict[str, Any]:
    execution = _state(request)["executions"].get(execution_id)
    if not execution:
        raise HTTPException(status_code=404)
    return execution


@router.get("/api/v1/executions/{execution_id}/task-plan")
async def execution_task_plan(request: Request, execution_id: str) -> list[dict[str, Any]]:
    execution = _state(request)["executions"].get(execution_id)
    if not execution:
        raise HTTPException(status_code=404)
    return [_execution_step(execution)]


@router.get("/api/v1/executions/{execution_id}/task-plan/{step_id}")
async def execution_task_plan_step(
    request: Request, execution_id: str, step_id: str
) -> dict[str, Any]:
    execution = _state(request)["executions"].get(execution_id)
    if not execution:
        raise HTTPException(status_code=404)
    step = _execution_step(execution)
    step["step_id"] = step_id
    return step


@router.get("/api/v1/executions/{execution_id}/reasoning-trace")
async def execution_reasoning_trace(
    request: Request, execution_id: str, step_id: str | None = Query(default=None)
) -> dict[str, Any]:
    execution = _state(request)["executions"].get(execution_id)
    if not execution:
        raise HTTPException(status_code=404)
    step = _execution_step(execution)
    if step_id:
        step["step_id"] = step_id
    return {
        "execution_id": execution_id,
        "steps": [
            {
                "step_id": step["step_id"],
                "technique": "workflow",
                "status": "completed",
                "summary": "E2E contract reasoning trace",
            }
        ],
    }


@router.get("/api/v1/executions/{execution_id}/journal")
async def execution_journal(request: Request, execution_id: str) -> dict[str, Any]:
    execution = _state(request)["executions"].get(execution_id)
    if not execution:
        raise HTTPException(status_code=404)
    return _items(
        [
            {
                "id": str(uuid4()),
                "execution_id": execution_id,
                "event_type": "execution.completed",
                "created_at": execution.get("completed_at"),
            }
        ]
    )


@router.post("/api/v1/executions/{execution_id}/rollback")
async def rollback_execution(
    request: Request, execution_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    del payload
    execution = _state(request)["executions"].get(execution_id)
    if not execution:
        raise HTTPException(status_code=404)
    execution["state"] = "completed"
    return execution


@router.post("/api/v1/executions/{execution_id}/reprioritize")
async def reprioritize_execution(
    request: Request, execution_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    execution = _state(request)["executions"].get(execution_id)
    if not execution:
        raise HTTPException(status_code=404)
    execution["priority"] = payload.get("priority")
    execution["completed_at"] = "2026-01-01T00:00:00+00:00"
    return execution


@router.get("/api/v1/runtime/warm-pool")
async def warm_pool(request: Request) -> dict[str, Any]:
    state = _state(request)
    return {
        "ready": int(state.get("warm_pool_ready") or 0),
        "capacity": int(state.get("warm_pool_capacity") or 0),
    }


@router.post("/api/v1/runtime/warm-pool/fill")
async def fill_warm_pool(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    size = max(int(payload.get("size") or 1), 0)
    state = _state(request)
    state["warm_pool_ready"] = size
    state["warm_pool_capacity"] = max(int(state.get("warm_pool_capacity") or 0), size)
    return {"ready": size, "capacity": state["warm_pool_capacity"]}


@router.post("/api/v1/runtime/warm-pool/drain")
async def drain_warm_pool(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    del payload
    state = _state(request)
    state["warm_pool_ready"] = 0
    return {
        "ready": 0,
        "capacity": int(state.get("warm_pool_capacity") or 0),
    }


@router.post("/api/v1/secrets", status_code=status.HTTP_201_CREATED)
async def create_secret(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    _state(request)["secrets"][payload.get("name")] = "[REDACTED]"
    return {"id": str(uuid4()), "name": payload.get("name")}


@router.get("/mcp/tools")
async def mcp_tools() -> dict[str, Any]:
    return _items([{"name": "mock-http-tool"}, {"name": "mock-code-tool"}])


@router.post("/mcp/call")
@router.post("/mcp/server/tools/{tool_name}/call")
async def mcp_call(payload: dict[str, Any], tool_name: str = "mock-http-tool") -> dict[str, Any]:
    return {"tool": payload.get("tool") or tool_name, "result": {"ok": True}}


@router.get("/mcp/server")
async def mcp_server() -> dict[str, Any]:
    return {"name": "musematic-e2e", "tools_endpoint": "/mcp/tools"}


@router.put("/api/v1/mcp/exposed-tools/{tool_id}")
async def expose_tool(tool_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"id": tool_id, **payload}


@router.post("/api/v1/evaluation/ab-tests", status_code=status.HTTP_201_CREATED)
async def create_ab_test(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    test_id = str(uuid4())
    item = {"id": test_id, "name": payload.get("name"), "variants": payload.get("variants", [])}
    _state(request)["ab_tests"][test_id] = item
    return item


@router.post("/api/v1/evaluation/ab-tests/{test_id}/executions")
async def ab_execution(request: Request, test_id: str) -> dict[str, Any]:
    test = _state(request)["ab_tests"].get(test_id)
    if not test:
        raise HTTPException(status_code=404)
    test["executions"] = int(test.get("executions", 0)) + 1
    return {"id": str(uuid4()), "test_id": test_id}


@router.get("/api/v1/evaluation/ab-tests/{test_id}/metrics")
async def ab_metrics(request: Request, test_id: str) -> dict[str, Any]:
    test = _state(request)["ab_tests"].get(test_id)
    if not test:
        raise HTTPException(status_code=404)
    return {"variants": test.get("variants", [])}


@router.post("/api/v1/evaluation/llm-judge")
async def llm_judge(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    score = {
        "execution_id": payload.get("execution_id"),
        "verdict": "pass",
        "dimensions": {"quality": 0.9},
    }
    _state(request)["scores"][payload.get("execution_id")] = score
    return score


@router.post("/api/v1/evaluation/trajectory-scores")
async def trajectory_score(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    score = {"execution_id": payload.get("execution_id"), "dimensions": {"trajectory": 1.0}}
    _state(request)["scores"][payload.get("execution_id")] = score
    return score


@router.get("/api/v1/evaluation/scores/{execution_id}")
async def get_score(request: Request, execution_id: str) -> dict[str, Any]:
    return _state(request)["scores"].get(
        execution_id, {"execution_id": execution_id, "dimensions": {}}
    )


@router.post("/api/v1/evaluations/eval-sets", status_code=status.HTTP_201_CREATED)
async def create_eval_set(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    eval_set = {"id": str(uuid4()), **payload}
    _state(request)["eval_sets"][eval_set["id"]] = eval_set
    return eval_set


@router.post(
    "/api/v1/evaluations/eval-sets/{eval_set_id}/cases",
    status_code=status.HTTP_201_CREATED,
)
async def create_eval_case(
    request: Request, eval_set_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    case = {"id": str(uuid4()), "eval_set_id": eval_set_id, **payload}
    _state(request)["eval_cases"].setdefault(eval_set_id, []).append(case)
    return case


@router.post(
    "/api/v1/evaluations/eval-sets/{eval_set_id}/run",
    status_code=status.HTTP_201_CREATED,
)
async def run_eval_set(
    request: Request, eval_set_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    run = {
        "id": str(uuid4()),
        "eval_set_id": eval_set_id,
        "status": "completed",
        "agent_fqn": payload.get("agent_fqn"),
        "agent_id": payload.get("agent_id"),
    }
    _state(request)["eval_runs"][run["id"]] = run
    return run


@router.get("/api/v1/evaluations/runs")
async def list_eval_runs(
    request: Request,
    agent_fqn: str | None = Query(default=None),
    page: int = Query(default=1),
    page_size: int = Query(default=20),
) -> dict[str, Any]:
    runs = list(_state(request)["eval_runs"].values())
    if agent_fqn:
        runs = [item for item in runs if item.get("agent_fqn") == agent_fqn]
    start = max(page - 1, 0) * page_size
    return {"items": runs[start : start + page_size], "total": len(runs)}


@router.get("/api/v1/evaluations/runs/{run_id}")
async def get_eval_run(request: Request, run_id: str) -> dict[str, Any]:
    run = _state(request)["eval_runs"].get(run_id)
    if not run:
        raise HTTPException(status_code=404)
    return run


@router.get("/api/v1/evaluations/runs/{run_id}/verdicts")
async def list_eval_verdicts(request: Request, run_id: str) -> dict[str, Any]:
    if run_id not in _state(request)["eval_runs"]:
        raise HTTPException(status_code=404)
    return _items([{"id": str(uuid4()), "run_id": run_id, "verdict": "pass"}])


@router.post("/api/v1/marketplace/search")
async def marketplace_search(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    state = _state(request)
    results = [
        _marketplace_listing(agent, state)
        for agent in state["agents"].values()
        if agent.get("status") == "published"
    ]
    return {
        "query": payload.get("query", ""),
        "has_results": bool(results),
        "results": results,
        "total": len(results),
    }


@router.get("/api/v1/marketplace/agents/{agent_id}/quality")
async def marketplace_quality(request: Request, agent_id: str) -> dict[str, Any]:
    agent = _agent_by_id(_state(request), agent_id)
    if not agent:
        raise HTTPException(status_code=404)
    certs = _certifications_for_agent(_state(request), str(agent["id"]))
    return {
        "agent_id": agent["id"],
        "certification_compliance": "certified"
        if any(item.get("status") == "active" for item in certs)
        else "uncertified",
        "has_data": True,
        "satisfaction_count": 1,
    }


@router.get("/api/v1/marketplace/agents/{agent_id}", response_model=None)
async def marketplace_agent(request: Request, agent_id: str) -> Any:
    state = _state(request)
    agent = _agent_by_id(state, agent_id)
    if not agent:
        raise HTTPException(status_code=404)
    workspace_id = _workspace_id_from_request(request)
    visibility_agents = list(agent.get("visibility_agents") or ["*"])
    if workspace_id != agent.get("workspace_id") and "*" not in visibility_agents:
        return JSONResponse(
            status_code=403,
            content={"error": {"code": "marketplace_visibility_denied".upper()}},
        )
    return _marketplace_listing(agent, state)


@router.post("/api/v1/agentops/{agent_fqn}/gate-check", status_code=status.HTTP_201_CREATED)
async def create_gate_check(
    request: Request, agent_fqn: str, payload: dict[str, Any]
) -> dict[str, Any]:
    check = {"id": str(uuid4()), "agent_fqn": agent_fqn, "status": "passed", **payload}
    _state(request)["gate_checks"].setdefault(agent_fqn, []).append(check)
    return check


@router.get("/api/v1/agentops/{agent_fqn}/gate-checks")
async def list_gate_checks(
    request: Request,
    agent_fqn: str,
    revision_id: str | None = Query(default=None),
    limit: int = Query(default=20),
) -> dict[str, Any]:
    checks = list(_state(request)["gate_checks"].get(agent_fqn, []))
    if revision_id:
        checks = [item for item in checks if item.get("revision_id") == revision_id]
    return _items(checks[:limit])


@router.post("/api/v1/agentops/drift-signals", status_code=status.HTTP_201_CREATED)
async def drift_signal(payload: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(uuid4()), **payload}


@router.post("/api/v1/agentops/proposals", status_code=status.HTTP_201_CREATED)
async def adaptation_proposal(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    proposal = {"id": str(uuid4()), "state": "proposed", **payload}
    _state(request)["proposals"][proposal["id"]] = proposal
    return proposal


@router.get("/api/v1/agentops/proposals/{proposal_id}")
async def get_proposal(request: Request, proposal_id: str) -> dict[str, Any]:
    return _state(request)["proposals"][proposal_id]


@router.post("/api/v1/agentops/canaries", status_code=status.HTTP_201_CREATED)
async def create_canary(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    canary = {"id": str(uuid4()), "state": "active", **payload}
    _state(request)["canaries"][canary["id"]] = canary
    return canary


@router.post("/api/v1/agentops/canaries/{canary_id}/rollback")
async def rollback_canary(
    request: Request, canary_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    canary = _state(request)["canaries"].get(canary_id, {"id": canary_id})
    canary.update({"state": "rolled_back", "reason": payload.get("reason")})
    return canary


@router.post("/api/v1/discovery/hypotheses", status_code=status.HTTP_201_CREATED)
async def create_hypothesis(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    item = {"id": str(uuid4()), **payload}
    _state(request)["hypotheses"][item["id"]] = item
    return item


@router.post("/api/v1/discovery/proximity-clusters/run")
async def run_clusters(request: Request) -> dict[str, Any]:
    ids = list(_state(request)["hypotheses"])
    _state(request)["clusters"] = [{"id": str(uuid4()), "members": ids}]
    return {"status": "completed"}


@router.get("/api/v1/discovery/proximity-clusters")
async def get_clusters(request: Request) -> dict[str, Any]:
    return _items(_state(request)["clusters"])


@router.get("/api/v1/fleets")
async def list_fleets(request: Request) -> dict[str, Any]:
    return _items(_state(request)["fleets"].values())


@router.post("/api/v1/fleets", status_code=status.HTTP_201_CREATED)
async def create_fleet(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or uuid4())
    fleet = {"id": name, "name": name, **payload}
    _state(request)["fleets"][name] = fleet
    return fleet


@router.delete("/api/v1/fleets/{fleet_name}")
async def delete_fleet(request: Request, fleet_name: str) -> Response:
    _state(request)["fleets"].pop(fleet_name, None)
    return Response(status_code=204)


@router.post("/api/v1/fleets/{fleet_name}/events")
async def fleet_event(request: Request, fleet_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    event = {"fleet": fleet_name, **payload}
    _record_event(request, "fleet.events", event)
    return event


@router.get("/api/v1/fleets/{fleet_name}/health")
async def fleet_health(fleet_name: str) -> dict[str, Any]:
    return {"fleet": fleet_name, "health": "healthy"}


@router.post("/api/v1/fleets/{fleet_name}/tasks", status_code=status.HTTP_201_CREATED)
async def fleet_task(request: Request, fleet_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    task = {
        "id": str(uuid4()),
        "fleet": fleet_name,
        "state": "completed",
        "subtasks_completed": 1,
        **payload,
    }
    _state(request)["fleet_tasks"][task["id"]] = task
    return task


@router.get("/api/v1/fleets/tasks/{task_id}")
async def get_fleet_task(request: Request, task_id: str) -> dict[str, Any]:
    return _state(request)["fleet_tasks"][task_id]


@router.post("/api/v1/governance/verdicts", status_code=status.HTTP_201_CREATED)
async def create_verdict(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    verdict = {"id": str(uuid4()), "verdict": "allow", **payload}
    _state(request)["verdicts"][verdict["id"]] = verdict
    _record_event(
        request,
        "governance.events",
        {"event_type": "governance.verdict.issued", "verdict": "allow"},
    )
    return verdict


@router.get("/api/v1/governance/verdicts/{verdict_id}")
async def get_verdict(request: Request, verdict_id: str) -> dict[str, Any]:
    return _state(request)["verdicts"][verdict_id]


@router.post("/api/v1/governance/enforcements", status_code=status.HTTP_201_CREATED)
async def create_enforcement(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    action = {"id": str(uuid4()), **payload}
    _record_event(
        request,
        "governance.events",
        {
            "event_type": "governance.enforcement.executed",
            "target_agent_fqn": payload.get("target_agent_fqn"),
        },
    )
    return action


@router.post("/api/v1/governance/pipeline/run", status_code=status.HTTP_201_CREATED)
async def governance_pipeline(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    execution = {"id": str(uuid4()), **payload}
    _record_event(
        request, "governance.events", {"event_type": "governance.verdict.issued", "verdict": "deny"}
    )
    _record_event(
        request,
        "governance.events",
        {"event_type": "governance.enforcement.executed", "execution_id": execution["id"]},
    )
    return execution


@router.get("/api/v1/audit/events")
async def audit_events() -> dict[str, Any]:
    return _items([])


@router.post("/api/v1/ibor/sync", status_code=status.HTTP_201_CREATED)
async def ibor_sync(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    sync = {"id": str(uuid4()), "status": "completed", **payload}
    _record_event(
        request, "ibor.events", {"event_type": "ibor.sync.completed", "sync_id": sync["id"]}
    )
    return sync


@router.post("/api/v1/interactions/attention", status_code=status.HTTP_201_CREATED)
async def attention(
    request: Request,
    payload: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    workspace_id = str(payload.get("workspace_id") or _workspace_id_from_request(request))
    target_identity = str(
        payload.get("target_identity") or payload.get("target_id") or _user_id(current_user)
    )
    source_agent_fqn = request.headers.get("x-agent-fqn") or str(
        payload.get("source_agent_fqn") or "default:seeded-executor"
    )
    goal_id = str(payload.get("related_goal_id") or request.headers.get("x-goal-id") or "")
    item = {
        "id": str(uuid4()),
        "workspace_id": workspace_id,
        "source_agent_fqn": source_agent_fqn,
        "target_identity": target_identity,
        "status": "pending",
        "created_at": _now(),
        **payload,
    }
    item["source_agent_fqn"] = source_agent_fqn
    item["target_identity"] = target_identity
    item["related_goal_id"] = goal_id or payload.get("related_goal_id")
    _state(request).setdefault("attention_requests", {})[item["id"]] = item
    _add_me_alert(
        request,
        user_id=target_identity,
        workspace_id=workspace_id,
        title="Attention requested",
        alert_type="attention_request",
        source_reference={"type": "attention_request", "id": item["id"]},
    )
    event_payload = {**item, "alert_already_created": True}
    _record_event(
        request,
        "interaction.events",
        {**event_payload, "key": target_identity, "event_type": "interaction.attention"},
    )
    await _emit_event(
        request,
        "interaction.attention",
        key=target_identity,
        event_type="attention.requested",
        payload=event_payload,
        workspace_id=workspace_id,
        interaction_id=str(payload.get("related_interaction_id"))
        if payload.get("related_interaction_id")
        else None,
        goal_id=goal_id or None,
        agent_fqn=source_agent_fqn,
        replay_after_seconds=1.0,
    )
    _record_ws(request, "attention", "attention.requested", event_payload)
    _record_ws(request, "attention", "request.created", event_payload)
    return JSONResponse(
        content=item,
        status_code=status.HTTP_201_CREATED,
        headers={"X-Goal-Id": request.headers.get("x-goal-id") or goal_id},
    )


@router.get("/api/v1/interactions/attention")
async def list_attention(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1),
    page_size: int = Query(default=50),
) -> dict[str, Any]:
    items = list(_state(request).setdefault("attention_requests", {}).values())
    if status_filter:
        items = [item for item in items if item.get("status") == status_filter]
    start = max(page - 1, 0) * page_size
    return {"items": items[start : start + page_size], "total": len(items)}


@router.post("/api/v1/interactions/attention/{attention_id}/resolve")
async def resolve_attention(
    request: Request, attention_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    del payload
    item = _state(request).setdefault("attention_requests", {}).get(attention_id)
    if not item:
        raise HTTPException(status_code=404)
    item["status"] = "resolved"
    item["resolved_at"] = _now()
    return item


@router.get("/api/v1/interactions")
async def list_interactions(
    request: Request,
    conversation_id: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
) -> dict[str, Any]:
    items = list(_state(request)["interactions"].values())
    if conversation_id:
        items = [item for item in items if item.get("conversation_id") == conversation_id]
    if workspace_id:
        items = [item for item in items if item.get("workspace_id") == workspace_id]
    return _items(items)


@router.post("/api/v1/interactions", status_code=status.HTTP_201_CREATED)
@router.post("/api/v1/interactions/", status_code=status.HTTP_201_CREATED)
async def create_interaction(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    workspace_id = str(payload.get("workspace_id") or _workspace_id_from_request(request))
    item = {
        "id": str(uuid4()),
        "workspace_id": workspace_id,
        "state": payload.get("state", "created"),
        "conversation_id": payload.get("conversation_id"),
        "goal_id": payload.get("goal_id"),
        "created_at": _now(),
        **payload,
    }
    _state(request)["interactions"][item["id"]] = item
    if gid := payload.get("gid"):
        _state(request)["goals"].setdefault(str(gid), {"gid": gid})["state"] = "in_progress"
    _record_event(request, "interaction.events", {"event_type": "interaction.created", **item})
    if gid := payload.get("gid"):
        _record_event(
            request, "execution.events", {"event_type": "execution.completed", "gid": gid}
        )
    return item


@router.post("/api/v1/interactions/{interaction_id}/transition")
async def transition_interaction(
    request: Request,
    interaction_id: str,
    payload: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    interaction = _state(request)["interactions"].get(interaction_id)
    if not interaction:
        raise HTTPException(status_code=404)
    trigger = str(payload.get("trigger") or payload.get("target_state") or "")
    old_state = str(interaction.get("state") or "created")
    new_state = {
        "ready": "ready",
        "start": "running",
        "complete": "completed",
    }.get(trigger, trigger or old_state)
    interaction["state"] = new_state
    interaction["updated_at"] = _now()
    conversation_id = interaction.get("conversation_id")
    workspace_id = str(interaction.get("workspace_id") or _workspace_id_from_request(request))
    if conversation_id and new_state in {"running", "completed"}:
        event_type = "interaction.started" if new_state == "running" else "interaction.completed"
        await _emit_event(
            request,
            "interaction.events",
            key=str(conversation_id),
            event_type=event_type,
            payload={
                "interaction_id": interaction_id,
                "conversation_id": conversation_id,
                "state": new_state,
            },
            workspace_id=workspace_id,
            conversation_id=str(conversation_id),
            interaction_id=interaction_id,
            goal_id=str(interaction.get("goal_id")) if interaction.get("goal_id") else None,
        )
    if new_state == "completed":
        user_id = _user_id(current_user)
        settings = _state(request).setdefault("me_alert_settings", {}).get(user_id, {})
        if "any_to_complete" in set(settings.get("state_transitions") or []):
            _add_me_alert(
                request,
                user_id=user_id,
                workspace_id=workspace_id,
                title="Interaction transitioned to completed",
                alert_type="state_transition",
                source_reference={"type": "interaction", "id": interaction_id},
            )
    return {**interaction, "old_state": old_state}


@router.post("/api/v1/interactions/{interaction_id}/messages", status_code=status.HTTP_201_CREATED)
async def create_interaction_message(
    request: Request, interaction_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    interaction = _state(request)["interactions"].get(interaction_id)
    if not interaction:
        raise HTTPException(status_code=404)
    message = {
        "id": str(uuid4()),
        "interaction_id": interaction_id,
        "conversation_id": interaction.get("conversation_id"),
        "workspace_id": interaction.get("workspace_id"),
        "message_type": payload.get("message_type", "user"),
        "content": payload.get("content"),
        "metadata": dict(payload.get("metadata") or {}),
        "created_at": _now(),
    }
    _state(request).setdefault("interaction_messages", {})[message["id"]] = message
    if conversation_id := interaction.get("conversation_id"):
        await _emit_event(
            request,
            "interaction.events",
            key=str(conversation_id),
            event_type="message.received",
            payload=message,
            workspace_id=str(interaction.get("workspace_id")),
            conversation_id=str(conversation_id),
            interaction_id=interaction_id,
            goal_id=str(interaction.get("goal_id")) if interaction.get("goal_id") else None,
        )
    return message


@router.get("/api/v1/interactions/{interaction_id}/messages")
async def list_interaction_messages(request: Request, interaction_id: str) -> dict[str, Any]:
    items = [
        item
        for item in _state(request).setdefault("interaction_messages", {}).values()
        if item.get("interaction_id") == interaction_id
    ]
    return _items(items)


@router.post("/api/v1/interactions/{interaction_id}/inject")
async def inject_interaction_message(
    request: Request, interaction_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    interaction = _state(request)["interactions"].get(interaction_id)
    if not interaction:
        raise HTTPException(status_code=404)
    message = {
        "id": str(uuid4()),
        "interaction_id": interaction_id,
        "conversation_id": interaction.get("conversation_id"),
        "workspace_id": interaction.get("workspace_id"),
        "message_type": "injection",
        "content": payload.get("content"),
        "metadata": dict(payload.get("metadata") or {}),
        "created_at": _now(),
    }
    _state(request).setdefault("interaction_messages", {})[message["id"]] = message
    if conversation_id := interaction.get("conversation_id"):
        await _emit_event(
            request,
            "interaction.events",
            key=str(conversation_id),
            event_type="message.received",
            payload=message,
            workspace_id=str(interaction.get("workspace_id")),
            conversation_id=str(conversation_id),
            interaction_id=interaction_id,
            goal_id=str(interaction.get("goal_id")) if interaction.get("goal_id") else None,
        )
    return message


@router.post("/api/v1/interactions/response-decisions", status_code=status.HTTP_201_CREATED)
async def response_decision(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    decision = {"id": str(uuid4()), **payload}
    if payload.get("attention_required"):
        alert = {
            "id": str(uuid4()),
            "source_id": decision["id"],
            "workspace_id": payload.get("workspace_id"),
            "state": "pending",
            "message": payload.get("message"),
        }
        _state(request)["alerts"][alert["id"]] = alert
    return decision


@router.post("/api/v1/interactions/alerts", status_code=status.HTTP_201_CREATED)
async def create_alert(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    alert = {"id": str(uuid4()), "state": "pending", **payload}
    _state(request)["alerts"][alert["id"]] = alert
    _record_ws(request, "alerts", "alert.created", alert)
    return alert


@router.get("/api/v1/interactions/alerts")
async def list_alerts(
    request: Request,
    state: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
) -> dict[str, Any]:
    items = list(_state(request)["alerts"].values())
    if state:
        items = [item for item in items if item.get("state") == state]
    if workspace_id:
        items = [item for item in items if item.get("workspace_id") == workspace_id]
    return _items(items)


@router.post("/api/v1/interactions/alerts/{alert_id}/dismiss")
async def dismiss_alert(request: Request, alert_id: str) -> dict[str, Any]:
    alert = _state(request)["alerts"].get(alert_id)
    if not alert:
        raise HTTPException(status_code=404)
    alert["state"] = "dismissed"
    return alert


@router.post("/api/v1/interactions/conversations", status_code=status.HTTP_201_CREATED)
async def create_conversation(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    workspace_id = str(payload.get("workspace_id") or _workspace_id_from_request(request))
    conversation = {
        "id": str(uuid4()),
        "workspace_id": workspace_id,
        "state": "open",
        "message_count": 0,
        "created_at": _now(),
        **payload,
    }
    _state(request)["conversations"][conversation["id"]] = conversation
    return _conversation_with_count(_state(request), conversation)


@router.get("/api/v1/interactions/conversations")
async def list_conversations(request: Request) -> dict[str, Any]:
    state = _state(request)
    workspace_id = _workspace_id_from_request(request)
    items = [
        _conversation_with_count(state, item)
        for item in state["conversations"].values()
        if item.get("workspace_id") == workspace_id
    ]
    return _items(items)


@router.post(
    "/api/v1/interactions/conversations/{conversation_id}/messages",
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation_message(
    request: Request, conversation_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    message = {"id": str(uuid4()), "conversation_id": conversation_id, **payload}
    _state(request)["conversation_messages"][message["id"]] = message
    return message


@router.post(
    "/api/v1/interactions/conversations/{conversation_id}/branches",
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation_branch(
    request: Request, conversation_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    branch = {"id": str(uuid4()), "conversation_id": conversation_id, "state": "active", **payload}
    _state(request)["conversation_branches"][branch["id"]] = branch
    return branch


@router.post("/api/v1/interactions/conversations/{conversation_id}/branches/{branch_id}/merge")
async def merge_branch(request: Request, conversation_id: str, branch_id: str) -> dict[str, Any]:
    del conversation_id
    branch = _state(request)["conversation_branches"].get(branch_id, {"id": branch_id})
    branch["state"] = "merged"
    return branch


@router.post("/api/v1/interactions/conversations/{conversation_id}/close")
async def close_conversation(request: Request, conversation_id: str) -> dict[str, Any]:
    conversation = _state(request)["conversations"].get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404)
    conversation["state"] = "closed"
    return conversation


@router.get("/api/v1/interactions/conversations/{conversation_id}")
async def get_conversation(request: Request, conversation_id: str) -> dict[str, Any]:
    state = _state(request)
    return _conversation_with_count(state, state["conversations"][conversation_id])


@router.get("/api/v1/interactions/conversations/{conversation_id}/interactions")
async def list_conversation_interactions(request: Request, conversation_id: str) -> dict[str, Any]:
    items = [
        item
        for item in _state(request)["interactions"].values()
        if item.get("conversation_id") == conversation_id
    ]
    return _items(items)


@router.post("/api/v1/_e2e/mock-llm/set-response")
async def set_mock_llm_response(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    prompt_pattern = str(payload.get("prompt_pattern") or "default")
    queue = _state(request).setdefault("mock_llm", {}).setdefault(prompt_pattern, [])
    queue.append(payload)
    return {"queue_depth": {prompt_pattern: len(queue)}}


@router.get("/api/v1/_e2e/mock-llm/calls")
async def list_mock_llm_calls(
    request: Request,
    pattern: str | None = Query(default=None),
    since: str | None = Query(default=None),
) -> dict[str, Any]:
    calls = list(_state(request).setdefault("mock_llm_calls", []))
    if pattern:
        calls = [
            item
            for item in calls
            if item.get("prompt_pattern") == pattern or item.get("pattern") == pattern
        ]
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            since_dt = None
        if since_dt is not None:
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=UTC)
            filtered_calls = []
            for item in calls:
                created_at = datetime.fromisoformat(str(item.get("created_at")))
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=UTC)
                if created_at >= since_dt:
                    filtered_calls.append(item)
            calls = filtered_calls
    return {"calls": calls}


@router.post("/api/v1/_e2e/mock-llm/clear")
async def clear_mock_llm(request: Request) -> dict[str, Any]:
    state = _state(request)
    state["mock_llm"] = {}
    state["mock_llm_calls"] = []
    return {"cleared": True}


@router.put("/api/v1/me/alert-settings")
async def put_me_alert_settings(
    request: Request,
    payload: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    user_id = _user_id(current_user)
    settings = {
        **_default_alert_settings(user_id),
        **payload,
        "user_id": user_id,
        "updated_at": _now(),
    }
    _state(request).setdefault("me_alert_settings", {})[user_id] = settings
    return settings


@router.get("/api/v1/me/alert-settings")
async def get_me_alert_settings(
    request: Request, current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    user_id = _user_id(current_user)
    return _state(request).setdefault("me_alert_settings", {}).setdefault(
        user_id, _default_alert_settings(user_id)
    )


@router.get("/api/v1/me/alerts")
async def list_me_alerts(
    request: Request,
    read: str | None = Query(default=None),
    limit: int = Query(default=50),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    user_id = _user_id(current_user)
    items = [
        item
        for item in _state(request)["alerts"].values()
        if item.get("user_id") == user_id
    ]
    if read == "unread":
        items = [item for item in items if not item.get("read")]
    elif read == "read":
        items = [item for item in items if item.get("read")]
    items = sorted(items, key=lambda item: str(item.get("created_at", "")), reverse=True)
    return {"items": items[:limit], "total": len(items)}


@router.patch("/api/v1/me/alerts/{alert_id}/read")
async def mark_me_alert_read(
    request: Request,
    alert_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    alert = _state(request)["alerts"].get(alert_id)
    if not alert or alert.get("user_id") != _user_id(current_user):
        raise HTTPException(status_code=404)
    alert["read"] = True
    alert["read_at"] = _now()
    return alert


@router.get("/api/v1/me/alerts/unread-count")
async def me_unread_alert_count(
    request: Request, current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    user_id = _user_id(current_user)
    count = sum(
        1
        for item in _state(request)["alerts"].values()
        if item.get("user_id") == user_id and not item.get("read")
    )
    return {"count": count}


@router.post("/api/v1/storage/artifacts", status_code=status.HTTP_201_CREATED)
async def create_artifact(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    if _state(request).get("s3_credentials_revoked"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="S3CredentialError: credentials revoked",
        )
    artifact_id = str(uuid4())
    content = str(payload.get("content") or "")
    checksum = payload.get("sha256") or hashlib.sha256(content.encode()).hexdigest()
    artifact = {
        "id": artifact_id,
        "state": "active",
        "content": content,
        "sha256": checksum,
        **payload,
    }
    _state(request)["artifacts"][artifact_id] = artifact
    return {key: value for key, value in artifact.items() if key != "content"}


@router.get("/api/v1/storage/artifacts/{artifact_id}/download")
async def download_artifact(request: Request, artifact_id: str) -> Response:
    artifact = _state(request)["artifacts"].get(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404)
    return Response(
        content=str(artifact.get("content", "")).encode(), media_type="application/octet-stream"
    )


@router.post("/api/v1/storage/artifacts/{artifact_id}/presign")
async def presign_artifact(artifact_id: str) -> dict[str, Any]:
    return {"url": f"https://e2e.invalid/artifacts/{artifact_id}"}


@router.post("/api/v1/storage/artifacts/{artifact_id}/archive")
async def archive_artifact(request: Request, artifact_id: str) -> dict[str, Any]:
    artifact = _state(request)["artifacts"].get(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404)
    artifact["state"] = "archived"
    _record_event(
        request,
        "storage.events",
        {"event_type": "storage.artifact.archived", "artifact_id": artifact_id},
    )
    return artifact


@router.get("/api/v1/storage/artifacts/{artifact_id}")
async def get_artifact(request: Request, artifact_id: str) -> dict[str, Any]:
    artifact = _state(request)["artifacts"].get(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404)
    return {key: value for key, value in artifact.items() if key != "content"}


@router.post("/api/v1/trust/certifiers", status_code=status.HTTP_201_CREATED)
async def create_certifier(payload: dict[str, Any]) -> dict[str, Any]:
    return {"id": payload.get("name", str(uuid4())), **payload}


@router.delete("/api/v1/trust/certifiers/{certifier_id}")
async def delete_certifier(certifier_id: str) -> Response:
    del certifier_id
    return Response(status_code=204)


@router.post("/api/v1/trust/certifications", status_code=status.HTTP_201_CREATED)
async def create_certification(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    cert = {"id": str(uuid4()), "status": "pending", **payload}
    _state(request)["certifications"][cert["id"]] = cert
    return cert


@router.post("/api/v1/trust/certifications/{cert_id}/evidence", status_code=status.HTTP_201_CREATED)
async def attach_certification_evidence(
    request: Request, cert_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    cert = _state(request)["certifications"].setdefault(
        cert_id, {"id": cert_id, "status": "pending"}
    )
    evidence = {"id": str(uuid4()), "certification_id": cert_id, **payload}
    cert.setdefault("evidence", []).append(evidence)
    return evidence


@router.post("/api/v1/trust/certifications/{cert_id}/activate")
async def activate_certification(request: Request, cert_id: str) -> dict[str, Any]:
    cert = _state(request)["certifications"].setdefault(cert_id, {"id": cert_id})
    cert["status"] = "active"
    return cert


@router.post("/api/v1/trust/certifications/{cert_id}/approve")
async def approve_certification(
    request: Request, cert_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    cert = _state(request)["certifications"].get(cert_id, {"id": cert_id})
    cert.update(payload)
    cert["status"] = "active"
    _state(request)["certifications"][cert_id] = cert
    return cert


@router.get("/api/v1/trust/certifications/{cert_id}")
async def get_certification(request: Request, cert_id: str) -> dict[str, Any]:
    return _state(request)["certifications"][cert_id]


@router.post("/api/v1/trust/certifications/{cert_id}/revoke")
async def revoke_certification(
    request: Request, cert_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    cert = _state(request)["certifications"].get(cert_id, {"id": cert_id})
    cert.update(payload)
    cert["status"] = "revoked"
    return cert


@router.post("/api/v1/trust/certifications/third-party")
async def third_party_certification(payload: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(uuid4()), "status": "active", "certifier": payload.get("certifier")}


@router.post("/api/v1/trust/contracts", status_code=status.HTTP_201_CREATED)
async def create_contract(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    contract = {"id": str(uuid4()), **payload}
    _state(request)["contracts"][contract["id"]] = contract
    return contract


@router.post("/api/v1/trust/signals", status_code=status.HTTP_201_CREATED)
async def create_trust_signal(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    signal = {"id": str(uuid4()), **payload}
    _state(request)["db_values"].setdefault("trust_signals", set()).add(signal["id"])
    _record_ws(request, "trust", "signal.created", signal)
    return signal


@router.get("/api/v1/trust/agents/{agent_fqn}/score")
async def trust_score(agent_fqn: str) -> dict[str, Any]:
    return {"agent_fqn": agent_fqn, "score": 0.99}


@router.post("/api/v1/policies/sanitize-output")
async def sanitize_output(payload: dict[str, Any]) -> dict[str, Any]:
    content = payload.get("content")
    if isinstance(content, dict):
        sanitized = {
            key: ("[REDACTED:secret]" if "token" in key.lower() else value)
            for key, value in content.items()
        }
        return {"content": sanitized}
    return {"content": content}


@router.post("/api/v1/policies", status_code=status.HTTP_201_CREATED)
async def create_policy(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    policy_id = str(payload.get("id") or payload.get("name") or uuid4())
    workspace_id = str(payload.get("workspace_id") or _workspace_id_from_request(request))
    policy = {
        **payload,
        "id": policy_id,
        "name": payload.get("name") or policy_id,
        "scope_type": payload.get("scope_type", "workspace"),
        "workspace_id": workspace_id,
        "rules": payload.get("rules", {}),
        "status": payload.get("status", "active"),
        "created_at": payload.get("created_at", _now()),
    }
    _state(request).setdefault("policies", {})[policy_id] = policy
    return policy


@router.get("/api/v1/policies")
async def list_policies(
    request: Request, workspace_id: str | None = Query(default=None)
) -> dict[str, Any]:
    policies = list(_state(request).setdefault("policies", {}).values())
    if workspace_id:
        policies = [item for item in policies if item.get("workspace_id") == workspace_id]
    return _items(policies)


@router.post("/api/v1/policies/bindings", status_code=status.HTTP_201_CREATED)
async def create_policy_binding(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    binding = {"id": str(uuid4()), **payload}
    _state(request).setdefault("policy_attachments", {})[binding["id"]] = binding
    return binding


@router.delete("/api/v1/policies/bindings/{binding_id}")
async def delete_policy_binding(request: Request, binding_id: str) -> Response:
    _state(request).setdefault("policy_attachments", {}).pop(binding_id, None)
    return Response(status_code=204)


@router.get("/api/v1/policies/{policy_id}")
async def get_policy(request: Request, policy_id: str) -> dict[str, Any]:
    policy = _state(request).setdefault("policies", {}).get(policy_id)
    if not policy:
        raise HTTPException(status_code=404)
    return policy


@router.post("/api/v1/policies/{policy_id}/attach", status_code=status.HTTP_201_CREATED)
async def attach_policy(
    request: Request, policy_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    if policy_id not in _state(request).setdefault("policies", {}):
        raise HTTPException(status_code=404)
    attachment = {"id": str(uuid4()), "policy_id": policy_id, **payload}
    _state(request).setdefault("policy_attachments", {})[attachment["id"]] = attachment
    return attachment


@router.delete("/api/v1/policies/{policy_id}")
async def delete_policy(request: Request, policy_id: str) -> Response:
    _state(request).setdefault("policies", {}).pop(policy_id, None)
    return Response(status_code=204)


@router.delete("/api/v1/users/{user_id}")
async def delete_user(user_id: str) -> Response:
    del user_id
    return Response(status_code=204)
