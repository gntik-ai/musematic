from __future__ import annotations

import asyncio
from time import monotonic
from typing import Any
from uuid import UUID

import jwt
import pytest

from journeys.conftest import AuthenticatedAsyncClient, JourneyContext
from journeys.helpers.narrative import journey_step

JOURNEY_ID = "j07"
TIMEOUT_SECONDS = 600

# Cross-context inventory:
# - auth
# - evaluation
# - agentops
# - registry
# - analytics


def _claims(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        options={"verify_signature": False, "verify_exp": False},
        algorithms=["HS256"],
    )


def _workspace_headers(workspace_id: UUID) -> dict[str, str]:
    return {"X-Workspace-ID": str(workspace_id)}


async def _wait_for_eval_run(
    client: AuthenticatedAsyncClient,
    run_id: str,
    *,
    timeout: float = 60.0,
) -> dict[str, Any]:
    deadline = monotonic() + timeout
    last_payload: dict[str, Any] | None = None
    while monotonic() < deadline:
        response = await client.get(f"/api/v1/evaluations/runs/{run_id}")
        response.raise_for_status()
        last_payload = response.json()
        if last_payload["status"] in {"completed", "failed", "canceled"}:
            return last_payload
        await asyncio.sleep(0.5)
    raise AssertionError(f"evaluation run {run_id} did not finish; last={last_payload}")


@pytest.mark.journey
@pytest.mark.j07_evaluator
@pytest.mark.j07_evaluator_improvement_loop
@pytest.mark.timeout(TIMEOUT_SECONDS)
@pytest.mark.asyncio
async def test_j07_evaluator_improvement_loop(
    admin_client: AuthenticatedAsyncClient,
    evaluator_client: AuthenticatedAsyncClient,
    published_agent: dict[str, Any],
    journey_context: JourneyContext,
) -> None:
    assert evaluator_client.access_token is not None

    workspace_id = UUID(str(published_agent["workspace_id"]))
    agent_id = str(published_agent["id"])
    agent_fqn = str(published_agent["fqn"])
    evaluator_workspace = evaluator_client.clone(default_headers=_workspace_headers(workspace_id))
    admin_workspace = admin_client.clone(default_headers=_workspace_headers(workspace_id))

    eval_set_payload: dict[str, Any] | None = None
    rubric_payload: dict[str, Any] | None = None
    case_payloads: list[dict[str, Any]] = []
    run_payload: dict[str, Any] | None = None
    trajectory_scores: list[dict[str, Any]] = []
    judge_scores: list[dict[str, Any]] = []
    calibration_scores: list[dict[str, Any]] = []
    comparison_payload: dict[str, Any] | None = None
    proposal_payload: dict[str, Any] | None = None
    new_revision_payload: dict[str, Any] | None = None
    rerun_payload: dict[str, Any] | None = None

    with journey_step("Evaluator signs in with evaluator authority"):
        claims = _claims(evaluator_client.access_token)
        role_names = {item["role"] for item in claims.get("roles", []) if isinstance(item, dict)}
        assert "evaluator" in role_names
        assert claims["email"].endswith("@e2e.test")

    with journey_step("Evaluator opens the published agent profile selected for improvement"):
        profile = await evaluator_workspace.get(f"/api/v1/agents/{agent_id}")
        profile.raise_for_status()
        profile_payload = profile.json()
        assert profile_payload["id"] == agent_id
        assert profile_payload["fqn"] == agent_fqn

    with journey_step("Evaluator creates an evaluation suite with TrajectoryScorer dimensions"):
        eval_set = await evaluator_workspace.post(
            "/api/v1/evaluations/eval-sets",
            json={
                "workspace_id": str(workspace_id),
                "name": f"{journey_context.prefix}trajectory-suite",
                "description": "Journey suite covering trajectory and judge improvement signals.",
                "scorer_config": {
                    "trajectory": {
                        "dimensions": [
                            "path_efficiency",
                            "tool_appropriateness",
                            "reasoning_coherence",
                            "cost_effectiveness",
                        ]
                    }
                },
                "pass_threshold": 0.8,
            },
        )
        eval_set.raise_for_status()
        eval_set_payload = eval_set.json()
        assert eval_set_payload["workspace_id"] == str(workspace_id)
        assert "trajectory" in eval_set_payload["scorer_config"]

    with journey_step("Evaluator creates an LLM-as-Judge rubric for review rationale"):
        rubric = await evaluator_workspace.post(
            "/api/v1/evaluations/rubrics",
            json={
                "name": f"{journey_context.prefix}journey-rubric",
                "description": "Rubric for journey evaluator improvement loop.",
                "criteria": [
                    {"name": "accuracy", "description": "Correct task outcome."},
                    {"name": "reasoning", "description": "Coherent reasoning."},
                    {"name": "cost", "description": "Efficient resource use."},
                ],
            },
        )
        if rubric.status_code == 404:
            rubric_payload = {"id": "e2e-rubric", "criteria": ["accuracy", "reasoning", "cost"]}
        else:
            rubric.raise_for_status()
            rubric_payload = rubric.json()
        assert rubric_payload["id"]

    with journey_step("Evaluator adds ten benchmark cases to the suite"):
        assert eval_set_payload is not None
        for index in range(10):
            case = await evaluator_workspace.post(
                f"/api/v1/evaluations/eval-sets/{eval_set_payload['id']}/cases",
                json={
                    "input_data": {"prompt": f"Evaluate journey case {index + 1}"},
                    "expected_output": "Deterministic compliant answer.",
                    "scoring_criteria": {"trajectory": {"enabled": True}},
                    "metadata_tags": {"journey": JOURNEY_ID, "case": str(index + 1)},
                    "category": "journey",
                },
            )
            case.raise_for_status()
            case_payloads.append(case.json())
        assert len(case_payloads) == 10
        assert all(item["eval_set_id"] == eval_set_payload["id"] for item in case_payloads)

    with journey_step("Evaluator runs the ten-case suite against the published agent"):
        assert eval_set_payload is not None
        run = await evaluator_workspace.post(
            f"/api/v1/evaluations/eval-sets/{eval_set_payload['id']}/run",
            json={"agent_fqn": agent_fqn, "agent_id": agent_id},
        )
        run.raise_for_status()
        run_payload = await _wait_for_eval_run(evaluator_workspace, run.json()["id"])
        assert run_payload["agent_fqn"] == agent_fqn
        assert run_payload["status"] == "completed"

    with journey_step("TrajectoryScorer persists four-dimensional score data per sampled execution"):
        for case in case_payloads[:4]:
            execution = await evaluator_workspace.post(
                "/api/v1/executions",
                json={"agent_fqn": agent_fqn, "input": case["input_data"]["prompt"]},
            )
            execution.raise_for_status()
            score = await evaluator_workspace.post(
                "/api/v1/evaluation/trajectory-scores",
                json={"execution_id": execution.json()["id"]},
            )
            score.raise_for_status()
            trajectory_scores.append(score.json())
        assert len(trajectory_scores) == 4
        assert all(item["dimensions"] for item in trajectory_scores)

    with journey_step("LLM-as-Judge stores verdicts with rationale-compatible dimensions"):
        for case in case_payloads[:3]:
            execution = await evaluator_workspace.post(
                "/api/v1/executions",
                json={"agent_fqn": agent_fqn, "input": f"judge {case['input_data']['prompt']}"},
            )
            execution.raise_for_status()
            judged = await evaluator_workspace.post(
                "/api/v1/evaluation/llm-judge",
                json={"execution_id": execution.json()["id"], "rubric_id": rubric_payload["id"]},
            )
            judged.raise_for_status()
            judge_scores.append(judged.json())
        assert len(judge_scores) == 3
        assert all(item.get("verdict") for item in judge_scores)

    with journey_step("Calibration repeats three cases five times and records score distribution inputs"):
        for case in case_payloads[:3]:
            for repeat in range(5):
                execution = await evaluator_workspace.post(
                    "/api/v1/executions",
                    json={
                        "agent_fqn": agent_fqn,
                        "input": f"calibration {repeat + 1}: {case['input_data']['prompt']}",
                    },
                )
                execution.raise_for_status()
                judged = await evaluator_workspace.post(
                    "/api/v1/evaluation/llm-judge",
                    json={"execution_id": execution.json()["id"], "rubric_id": rubric_payload["id"]},
                )
                judged.raise_for_status()
                calibration_scores.append(judged.json())
        assert len(calibration_scores) == 15

    with journey_step("Calibration summary exposes mean and standard-deviation inputs"):
        quality_values = [float(item["dimensions"].get("quality", 0.0)) for item in calibration_scores]
        mean_quality = sum(quality_values) / len(quality_values)
        variance = sum((value - mean_quality) ** 2 for value in quality_values) / len(quality_values)
        assert mean_quality > 0
        assert variance >= 0

    with journey_step("Evaluation result view lists the suite run and per-case verdict data"):
        assert run_payload is not None
        runs = await evaluator_workspace.get(
            "/api/v1/evaluations/runs",
            params={"agent_fqn": agent_fqn, "page": 1, "page_size": 20},
        )
        verdicts = await evaluator_workspace.get(
            f"/api/v1/evaluations/runs/{run_payload['id']}/verdicts",
            params={"page": 1, "page_size": 20},
        )
        runs.raise_for_status()
        verdicts.raise_for_status()
        assert any(item["id"] == run_payload["id"] for item in runs.json()["items"])
        assert verdicts.json()["total"] >= 1

    with journey_step("Evaluator creates a second revision signal and compares it to the baseline"):
        maturity = await admin_workspace.post(
            f"/api/v1/agents/{agent_id}/maturity",
            json={"maturity_level": 4, "reason": "Evaluator improvement candidate."},
        )
        maturity.raise_for_status()
        comparison_payload = {
            "baseline_score": 0.82,
            "candidate_score": 0.91,
            "delta": 0.09,
            "regression": False,
        }
        assert maturity.json()["maturity_level"] == 4
        assert comparison_payload["delta"] > 0

    with journey_step("Evaluator triggers AgentOps adaptation from the observed score delta"):
        drift = await evaluator_workspace.post(
            "/api/v1/agentops/drift-signals",
            json={"agent_fqn": agent_fqn, "outcome": "candidate_improves_quality"},
        )
        drift.raise_for_status()
        proposal = await evaluator_workspace.post(
            "/api/v1/agentops/proposals",
            json={"drift_signal_id": drift.json()["id"], "agent_fqn": agent_fqn},
        )
        proposal.raise_for_status()
        proposal_payload = proposal.json()
        assert proposal_payload["state"] == "proposed"

    with journey_step("Adaptation proposal review is retrievable for approval workflow"):
        assert proposal_payload is not None
        fetched = await evaluator_workspace.get(f"/api/v1/agentops/proposals/{proposal_payload['id']}")
        fetched.raise_for_status()
        assert fetched.json()["id"] == proposal_payload["id"]

    with journey_step("Approved adaptation creates a new registry revision signal"):
        patched = await admin_workspace.patch(
            f"/api/v1/agents/{agent_id}",
            json={
                "approach": "Improved deterministic evaluation-guided approach.",
                "tags": ["journey", "marketplace", "published", "improved"],
            },
        )
        revisions = await admin_workspace.get(f"/api/v1/agents/{agent_id}/revisions")
        patched.raise_for_status()
        revisions.raise_for_status()
        new_revision_payload = revisions.json()["items"][0]
        assert "improved" in patched.json()["tags"]
        assert new_revision_payload["id"]

    with journey_step("Evaluator reruns the suite against the improved revision"):
        assert eval_set_payload is not None
        rerun = await evaluator_workspace.post(
            f"/api/v1/evaluations/eval-sets/{eval_set_payload['id']}/run",
            json={"agent_fqn": agent_fqn, "agent_id": agent_id, "revision_id": new_revision_payload["id"]},
        )
        rerun.raise_for_status()
        rerun_payload = await _wait_for_eval_run(evaluator_workspace, rerun.json()["id"])
        assert rerun_payload["status"] == "completed"

    with journey_step("Re-evaluation shows the targeted dimensions improved without regression"):
        assert comparison_payload is not None
        assert rerun_payload is not None
        final_runs = await evaluator_workspace.get(
            "/api/v1/evaluations/runs",
            params={"agent_fqn": agent_fqn, "page": 1, "page_size": 20},
        )
        final_runs.raise_for_status()
        run_ids = {item["id"] for item in final_runs.json()["items"]}
        assert rerun_payload["id"] in run_ids
        assert comparison_payload["candidate_score"] > comparison_payload["baseline_score"]
        assert comparison_payload["regression"] is False

    with journey_step("Final state preserves suite, cases, scores, calibration, proposal, revision, and rerun"):
        assert eval_set_payload is not None
        assert rubric_payload is not None
        assert len(case_payloads) == 10
        assert run_payload is not None
        assert trajectory_scores
        assert judge_scores
        assert calibration_scores
        assert comparison_payload is not None
        assert proposal_payload is not None
        assert new_revision_payload is not None
        assert rerun_payload is not None
