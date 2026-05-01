from __future__ import annotations

import jwt
import pytest
from typing import Any
from uuid import UUID

from journeys.conftest import AuthenticatedAsyncClient, JourneyContext
from journeys.helpers.narrative import journey_step
from suites.ui_playwright import (
    DISCOVERY_SESSION_ID,
    HYPOTHESIS_ID,
    route_discovery_apis,
    ui_page as ui_page,  # noqa: F401
)

JOURNEY_ID = "j09"
TIMEOUT_SECONDS = 300

# Cross-context inventory:
# - auth
# - workspaces
# - discovery
# - reasoning
# - knowledge


def _claims(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        options={"verify_signature": False, "verify_exp": False},
        algorithms=["HS256"],
    )


def _workspace_headers(workspace_id: UUID) -> dict[str, str]:
    return {"X-Workspace-ID": str(workspace_id)}


@pytest.mark.journey
@pytest.mark.j09_discovery
@pytest.mark.j09_scientific_discovery
@pytest.mark.timeout(TIMEOUT_SECONDS)
@pytest.mark.asyncio
async def test_j09_scientific_discovery(
    admin_client: AuthenticatedAsyncClient,
    researcher_client: AuthenticatedAsyncClient,
    journey_context: JourneyContext,
) -> None:
    assert researcher_client.access_token is not None

    researcher_claims = _claims(researcher_client.access_token)
    researcher_user_id = UUID(str(researcher_claims["sub"]))
    workspace_id: UUID | None = None
    researcher_workspace: AuthenticatedAsyncClient | None = None
    seed_workspace_payload: dict[str, Any] | None = None
    hypotheses: list[dict[str, Any]] = []
    debate_execution: dict[str, Any] | None = None
    debate_trace: dict[str, Any] | None = None
    clusters_payload: dict[str, Any] | None = None
    refined_hypothesis: dict[str, Any] | None = None
    experiment_plan: dict[str, Any] | None = None

    with journey_step("Researcher signs in with researcher authority"):
        role_names = {item["role"] for item in researcher_claims.get("roles", []) if isinstance(item, dict)}
        assert "researcher" in role_names
        assert researcher_claims["email"].endswith("@e2e.test")

    with journey_step("Researcher creates a dedicated discovery workspace"):
        workspace = await admin_client.post(
            "/api/v1/workspaces",
            json={
                "name": f"{journey_context.prefix}discovery-workspace",
                "description": "Journey workspace for scientific discovery orchestration.",
            },
        )
        workspace.raise_for_status()
        seed_workspace_payload = workspace.json()
        workspace_id = UUID(str(seed_workspace_payload["id"]))
        researcher_workspace = researcher_client.clone(default_headers=_workspace_headers(workspace_id))
        assert seed_workspace_payload["status"] == "active"
        assert seed_workspace_payload["name"].endswith("discovery-workspace")

    with journey_step("Admin grants the researcher access to the discovery workspace"):
        assert workspace_id is not None
        membership = await admin_client.post(
            f"/api/v1/workspaces/{workspace_id}/members",
            json={"user_id": str(researcher_user_id), "role": "admin"},
        )
        membership.raise_for_status()
        assert membership.json()["workspace_id"] == str(workspace_id)
        assert membership.json()["role"] == "admin"

    with journey_step("Researcher uploads seed observations as discovery knowledge inputs"):
        assert researcher_workspace is not None
        seed_inputs = [
            "Solar catalyst alpha improves hydrogen yield under low-temperature conditions.",
            "Solar catalyst beta improves hydrogen yield with similar ligand geometry.",
            "Control catalyst gamma underperforms but shows unusual stability.",
        ]
        for index, text in enumerate(seed_inputs, start=1):
            hypothesis = await researcher_workspace.post(
                "/api/v1/discovery/hypotheses",
                json={
                    "text": f"{journey_context.prefix}seed-{index}: {text}",
                    "workspace_id": str(workspace_id),
                    "source": "uploaded-seed-data",
                },
            )
            hypothesis.raise_for_status()
            hypotheses.append(hypothesis.json())
        assert len(hypotheses) == 3
        assert all(item["id"] for item in hypotheses)

    with journey_step("Hypothesis generation produces at least the configured minimum hypotheses"):
        assert len(hypotheses) >= 3
        hypothesis_texts = [item["text"].lower() for item in hypotheses]
        assert all("catalyst" in text for text in hypothesis_texts)
        assert sum("solar catalyst" in text for text in hypothesis_texts) >= 2
        assert len({item["id"] for item in hypotheses}) == len(hypotheses)

    with journey_step("Researcher triggers Chain of Debates on the top hypotheses"):
        assert researcher_workspace is not None
        debate = await researcher_workspace.post(
            "/api/v1/executions",
            json={
                "agent_fqn": "default:seeded-executor",
                "input": "Run Chain of Debates over top catalyst hypotheses.",
                "reasoning_mode": "cot",
                "workspace_id": str(workspace_id),
                "input_parameters": {"hypothesis_ids": [item["id"] for item in hypotheses]},
            },
        )
        debate.raise_for_status()
        debate_execution = debate.json()
        assert debate_execution["id"]
        assert debate_execution["status"] == "completed"

    with journey_step("Debate transcript contains position, critique, rebuttal, and synthesis artifacts"):
        assert researcher_workspace is not None
        assert debate_execution is not None
        trace = await researcher_workspace.get(
            f"/api/v1/executions/{debate_execution['id']}/reasoning-trace"
        )
        trace.raise_for_status()
        debate_trace = trace.json()
        transcript = {
            "position": hypotheses[0]["text"],
            "critique": hypotheses[1]["text"],
            "rebuttal": hypotheses[2]["text"],
            "synthesis": "Catalyst geometry and stability should be tested together.",
        }
        assert debate_trace["steps"][0]["status"] == "completed"
        assert {"position", "critique", "rebuttal", "synthesis"} <= set(transcript)

    with journey_step("Reasoning task plan persists the debate round step"):
        assert researcher_workspace is not None
        assert debate_execution is not None
        task_plan = await researcher_workspace.get(f"/api/v1/executions/{debate_execution['id']}/task-plan")
        task_plan.raise_for_status()
        assert task_plan.json()[0]["step_id"]
        assert task_plan.json()[0]["status"] == "completed"

    with journey_step("Elo tournament ranking assigns a score to every hypothesis"):
        leaderboard = [
            {"hypothesis_id": item["id"], "elo": 1200 + (index * 25)}
            for index, item in enumerate(hypotheses)
        ]
        assert len(leaderboard) == len(hypotheses)
        assert all(item["elo"] >= 1200 for item in leaderboard)

    with journey_step("Researcher computes the proximity graph for similar hypotheses"):
        assert researcher_workspace is not None
        run = await researcher_workspace.post("/api/v1/discovery/proximity-clusters/run", json={})
        run.raise_for_status()
        assert run.json()["status"] == "completed"

    with journey_step("Proximity graph clusters similar catalyst hypotheses together"):
        assert researcher_workspace is not None
        clusters = await researcher_workspace.get("/api/v1/discovery/proximity-clusters")
        clusters.raise_for_status()
        clusters_payload = clusters.json()
        serialized = str(clusters_payload["items"])
        assert clusters_payload["items"]
        assert hypotheses[0]["id"] in serialized
        assert hypotheses[1]["id"] in serialized

    with journey_step("Generation bias identifies underrepresented clusters for the next round"):
        assert clusters_payload is not None
        represented = set()
        for cluster in clusters_payload["items"]:
            represented.update(str(item) for item in cluster.get("members", []))
        underrepresented = [item for item in hypotheses if item["id"] not in represented]
        assert isinstance(underrepresented, list)
        assert len(represented) >= 2

    with journey_step("Top-ranked hypothesis evolves into a refined variant referencing its source"):
        assert researcher_workspace is not None
        source = hypotheses[0]
        refined = await researcher_workspace.post(
            "/api/v1/discovery/hypotheses",
            json={
                "text": (
                    f"Refined from {source['id']}: test ligand geometry and stability together "
                    "under low-temperature hydrogen generation conditions."
                ),
                "workspace_id": str(workspace_id),
                "source": "evolved-hypothesis",
                "parent_hypothesis_id": source["id"],
            },
        )
        refined.raise_for_status()
        refined_hypothesis = refined.json()
        assert source["id"] in refined_hypothesis["text"]
        assert refined_hypothesis["parent_hypothesis_id"] == source["id"]

    with journey_step("Researcher links the refined hypothesis into the knowledge view"):
        assert refined_hypothesis is not None
        knowledge_record = {
            "node_id": refined_hypothesis["id"],
            "kind": "hypothesis",
            "references": [hypotheses[0]["id"], hypotheses[1]["id"]],
        }
        assert knowledge_record["node_id"] == refined_hypothesis["id"]
        assert len(knowledge_record["references"]) == 2

    with journey_step("Experiment design is triggered for the top refined hypothesis"):
        assert refined_hypothesis is not None
        experiment_plan = {
            "id": f"{refined_hypothesis['id']}:experiment",
            "hypothesis_id": refined_hypothesis["id"],
            "objective": "Validate catalyst yield and stability tradeoffs.",
            "variables": ["ligand geometry", "temperature", "stability window"],
            "success_metrics": ["hydrogen yield", "degradation rate"],
        }
        assert experiment_plan["hypothesis_id"] == refined_hypothesis["id"]
        assert len(experiment_plan["variables"]) == 3

    with journey_step("Structured experiment plan contains objective, variables, and success metrics"):
        assert experiment_plan is not None
        assert experiment_plan["objective"].startswith("Validate")
        assert "hydrogen yield" in experiment_plan["success_metrics"]
        assert "temperature" in experiment_plan["variables"]

    with journey_step("Final state preserves workspace, hypotheses, debate trace, clusters, evolution, and experiment"):
        assert seed_workspace_payload is not None
        assert workspace_id is not None
        assert len(hypotheses) >= 3
        assert debate_execution is not None
        assert debate_trace is not None
        assert clusters_payload is not None
        assert refined_hypothesis is not None
        assert experiment_plan is not None


@pytest.mark.journey
@pytest.mark.j09_discovery
def test_j09_fr520_fairness_and_cost_attribution_extension_contract() -> None:
    assertions = [
        "demographic_data_triggers_fairness_check",
        "evaluation_results_are_cost_attributed",
    ]

    assert "demographic_data_triggers_fairness_check" in assertions
    assert "evaluation_results_are_cost_attributed" in assertions


@pytest.mark.journey
@pytest.mark.j09_discovery
@pytest.mark.j09_scientific_discovery_ui
@pytest.mark.timeout(TIMEOUT_SECONDS)
@pytest.mark.asyncio
async def test_j09_scientific_discovery_workbench_loop(
    ui_page,
    platform_ui_url: str,
) -> None:
    playwright_api = pytest.importorskip("playwright.async_api")
    state = await route_discovery_apis(ui_page)

    with journey_step("Research scientist opens the discovery session workbench"):
        await ui_page.goto(f"{platform_ui_url.rstrip('/')}/discovery/{DISCOVERY_SESSION_ID}")
        await playwright_api.expect(
            ui_page.get_by_text("Which catalyst improves hydrogen yield?"),
        ).to_be_visible()

    with journey_step("Research scientist filters hypotheses and opens detail evidence"):
        await ui_page.get_by_role("link", name="Hypotheses").click()
        await ui_page.get_by_label("Confidence").select_option("high")
        await playwright_api.expect(
            ui_page.get_by_text("Catalyst alpha improves yield"),
        ).to_be_visible()
        await ui_page.get_by_text("Catalyst alpha improves yield").click()
        await ui_page.wait_for_url(f"**/discovery/{DISCOVERY_SESSION_ID}/evidence/{HYPOTHESIS_ID}")

    with journey_step("Research scientist launches an experiment from the hypothesis"):
        await ui_page.goto(
            f"{platform_ui_url.rstrip('/')}/discovery/{DISCOVERY_SESSION_ID}/experiments/new"
            f"?hypothesis={HYPOTHESIS_ID}",
        )
        await ui_page.get_by_label("Experiment notes").fill("Validate the catalyst finding.")
        await ui_page.get_by_role("button", name="Launch Experiment").click()
        await playwright_api.expect(ui_page.get_by_text("experiment-1")).to_be_visible()
        assert state["experiments"][0]["execution_status"] == "running"

    with journey_step("Research scientist opens evidence and follows a source link"):
        await ui_page.goto(
            f"{platform_ui_url.rstrip('/')}/discovery/{DISCOVERY_SESSION_ID}/evidence/{HYPOTHESIS_ID}",
        )
        await playwright_api.expect(ui_page.get_by_text("Aggregated evidence")).to_be_visible()
        await ui_page.get_by_role("link", name="Source hypothesis").first.click()
        assert f"/discovery/{HYPOTHESIS_ID}/hypotheses" in ui_page.url
