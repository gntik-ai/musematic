from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse, StreamingResponse

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
        "workspaces": {
            BASE_WORKSPACE_ID: {
                "id": BASE_WORKSPACE_ID,
                "name": "test-workspace-alpha",
                "display_name": "test-workspace-alpha",
            }
        },
        "workspace_name_index": {"test-workspace-alpha": BASE_WORKSPACE_ID},
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
        "alerts": {},
        "artifacts": {},
        "certifications": {},
        "contracts": {},
        "secrets": {},
        "visibility_grants": set(),
        "events": {},
        "ws_events": [],
        "db_values": {},
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
            "workspace_id": BASE_WORKSPACE_ID,
            "status": "active",
        }
    request.app.state.e2e_contract_state = state
    return state


def _items(values: Any) -> dict[str, Any]:
    return {"items": list(values)}


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


def _stable_output(payload: dict[str, Any]) -> str:
    if payload.get("prompt_pattern") == "agent_response":
        return "fixed-alpha"
    return "ok"


@router.get("/api/v1/_e2e/contract/events")
async def contract_events(request: Request, topic: str = Query(...)) -> dict[str, Any]:
    return _items(_event_store(request, topic))


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
        yield "event: started\n\n"
        yield "event: completed\n\n"

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
    return {"secret": "JBSWY3DPEHPK3PXP", "recovery_codes": ["recovery-e2e"]}


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
        "local_name": local_name,
        "fqn": fqn,
        "role_type": payload.get("role_type", "executor"),
        "workspace_id": payload.get("workspace_id", BASE_WORKSPACE_ID),
    }
    agents[fqn] = agent
    return agent


@router.post("/api/v1/agents/upload", status_code=status.HTTP_201_CREATED)
async def upload_agent(request: Request, namespace_name: str = "default") -> dict[str, Any]:
    fqn = f"{namespace_name}:seeded-{uuid4().hex[:8]}"
    _state(request)["agents"].setdefault(
        fqn,
        {
            "id": fqn,
            "namespace": namespace_name,
            "local_name": fqn.split(":", 1)[1],
            "fqn": fqn,
            "role_type": "executor",
            "workspace_id": BASE_WORKSPACE_ID,
        },
    )
    return {"created": True, **_state(request)["agents"][fqn]}


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
    workspace_id: str | None = Query(default=None),
) -> dict[str, Any]:
    del workspace_id
    agents = list(_state(request)["agents"].values())
    if namespace:
        agents = [item for item in agents if item.get("namespace") == namespace]
    return _items(agents)


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


@router.post("/api/v1/trust/agents/{agent_id}/certifications", status_code=status.HTTP_201_CREATED)
async def certify_agent(agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(uuid4()), "agent_id": agent_id, "status": payload.get("status", "active")}


@router.get("/api/v1/agents/{fqn}")
async def get_agent(
    request: Request,
    fqn: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    item = _state(request)["agents"].get(fqn)
    if not item:
        raise HTTPException(status_code=404)
    if fqn.startswith("test-finance:") and not _is_admin(current_user):
        if fqn not in _state(request)["visibility_grants"]:
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
    }
    state["workspaces"][workspace_id] = workspace
    state["workspace_name_index"][name] = workspace_id
    return workspace


@router.get("/api/v1/workspaces")
async def list_workspaces(request: Request) -> dict[str, Any]:
    return _items(_state(request)["workspaces"].values())


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
    goal_id = str(uuid4())
    goal = {
        "id": goal_id,
        "gid": goal_id,
        "workspace_id": workspace_id,
        "title": payload.get("title"),
        "state": "open",
    }
    _state(request)["goals"][goal_id] = goal
    return goal


@router.patch("/api/v1/workspaces/{workspace_id}/goals/{goal_id}")
async def patch_goal(
    request: Request, workspace_id: str, goal_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    del workspace_id
    goal = _state(request)["goals"].setdefault(goal_id, {"id": goal_id, "gid": goal_id})
    goal["state"] = payload.get("status") or payload.get("state") or goal.get("state", "open")
    return goal


@router.get("/api/v1/workspaces/{workspace_id}/goals/{goal_id}")
async def get_goal(request: Request, workspace_id: str, goal_id: str) -> dict[str, Any]:
    del workspace_id
    goal = _state(request)["goals"].setdefault(
        goal_id,
        {"id": goal_id, "gid": goal_id, "workspace_id": BASE_WORKSPACE_ID, "state": "open"},
    )
    return goal


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
    if "ignore previous instructions" in str(payload.get("input", "")).lower():
        _record_event(
            request,
            "trust.events",
            {"event_type": "trust.screener.blocked", "agent_fqn": payload.get("agent_fqn")},
        )
        raise HTTPException(status_code=400, detail="blocked by E2E pre-screener")

    execution_id = str(uuid4())
    execution = {
        "id": execution_id,
        "state": "completed",
        "status": "completed",
        "agent_fqn": payload.get("agent_fqn"),
        "input": payload.get("input"),
        "response": _stable_output(payload),
        "output": _stable_output(payload),
        "completed_at": "2026-01-01T00:00:00+00:00",
    }
    _state(request)["executions"][execution_id] = execution
    event = {"execution_id": execution_id, **_execution_event_for(payload)}
    if payload.get("gid"):
        event["gid"] = payload["gid"]
    _record_event(request, "execution.events", event)
    _record_ws(request, "runtime", "warm_pool.replenished", {"ready": 1})
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
async def warm_pool() -> dict[str, Any]:
    return {"ready": 1, "capacity": 1}


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
async def attention(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    item = {"id": str(uuid4()), **payload}
    _record_event(request, "interaction.events", {"event_type": "interaction.attention", **item})
    _record_ws(request, "attention", "request.created", item)
    return item


@router.post("/api/v1/interactions", status_code=status.HTTP_201_CREATED)
async def create_interaction(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    item = {"id": str(uuid4()), **payload}
    _state(request)["interactions"][item["id"]] = item
    if gid := payload.get("gid"):
        _state(request)["goals"].setdefault(str(gid), {"gid": gid})["state"] = "in_progress"
    _record_event(request, "interaction.events", {"event_type": "interaction.created", **item})
    if gid := payload.get("gid"):
        _record_event(
            request, "execution.events", {"event_type": "execution.completed", "gid": gid}
        )
    return item


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
    conversation = {"id": str(uuid4()), "state": "open", **payload}
    _state(request)["conversations"][conversation["id"]] = conversation
    return conversation


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
    return _state(request)["conversations"][conversation_id]


@router.post("/api/v1/storage/artifacts", status_code=status.HTTP_201_CREATED)
async def create_artifact(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
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
async def create_policy(payload: dict[str, Any]) -> dict[str, Any]:
    return {"id": payload.get("name", str(uuid4())), **payload}


@router.get("/api/v1/policies")
async def list_policies() -> dict[str, Any]:
    return _items([])


@router.delete("/api/v1/policies/{policy_id}")
async def delete_policy(policy_id: str) -> Response:
    del policy_id
    return Response(status_code=204)


@router.post("/api/v1/policies/bindings", status_code=status.HTTP_201_CREATED)
async def create_policy_binding(payload: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(uuid4()), **payload}


@router.delete("/api/v1/policies/bindings/{binding_id}")
async def delete_policy_binding(binding_id: str) -> Response:
    del binding_id
    return Response(status_code=204)


@router.delete("/api/v1/users/{user_id}")
async def delete_user(user_id: str) -> Response:
    del user_id
    return Response(status_code=204)
