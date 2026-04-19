from __future__ import annotations

from platform.evaluation.scorers.llm_judge import LLMJudgeScorer
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from tests.evaluation_testing_support import make_settings


@pytest.mark.asyncio
async def test_llm_judge_score_resolves_rubric_id_and_clamps_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rubric_id = uuid4()
    rubric = SimpleNamespace(
        id=rubric_id,
        version=3,
        name="custom",
        criteria=[
            {"name": "accuracy", "description": "Correctness", "scale_min": 1, "scale_max": 5},
            {"name": "completeness", "description": "Coverage", "scale_min": 1, "scale_max": 5},
        ],
    )
    scorer = LLMJudgeScorer(
        settings=make_settings(),
        rubric_service=SimpleNamespace(get_rubric_model=AsyncMock(return_value=rubric)),
    )

    async def _fake_judge_with_retries(**_kwargs: object) -> dict[str, object]:
        return {
            "criteria_scores": {"accuracy": 8.0, "completeness": 0.0},
            "rationale": "parsed",
            "raw_payload": {"raw": True},
        }

    monkeypatch.setattr(scorer, "_judge_with_retries", _fake_judge_with_retries)
    result = await scorer.score(
        "actual",
        "expected",
        {
            "judge_model": "judge-v1",
            "rubric_id": str(rubric_id),
            "threshold": 3.0,
            "principal_id": "principal-1",
        },
    )

    assert result.score == 3.0
    assert result.passed is True
    assert result.extra["rubric_id"] == str(rubric_id)
    assert result.extra["rubric_version"] == 3
    assert result.extra["rubric_name"] == "custom"
    assert result.extra["raw_judge_output"] == {"raw": True}
    assert result.extra["out_of_range_clamped"] == {
        "accuracy": {"original": 8.0, "clamped": 5.0},
        "completeness": {"original": 0.0, "clamped": 1.0},
    }


@pytest.mark.asyncio
async def test_llm_judge_retries_transient_provider_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scorer = LLMJudgeScorer(settings=make_settings(), api_url="https://judge.example")
    attempts = 0

    async def _fake_once_provider(**_kwargs: object) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.TimeoutException("slow")
        return {
            "score": 4.0,
            "criteria_scores": {"factual_accuracy": 4.0, "completeness": 4.0},
            "rationale": "ok",
            "raw_payload": {"attempt": attempts},
        }

    monkeypatch.setattr(scorer, "_judge_once_provider", _fake_once_provider)
    result = await scorer.score(
        "actual",
        "expected",
        {
            "judge_model": "judge-v1",
            "rubric": {"template": "correctness"},
            "calibration_runs": 1,
        },
    )

    assert attempts == 2
    assert result.error is None
    assert result.score == 4.0
    assert result.extra["raw_judge_output"] == {"attempt": 2}


@pytest.mark.asyncio
async def test_llm_judge_marks_permanent_failures_without_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scorer = LLMJudgeScorer(settings=make_settings(), api_url="https://judge.example")

    async def _fake_once_provider(**_kwargs: object) -> dict[str, object]:
        raise ValueError("bad payload")

    monkeypatch.setattr(scorer, "_judge_once_provider", _fake_once_provider)
    result = await scorer.score(
        "actual",
        "expected",
        {
            "judge_model": "judge-v1",
            "rubric": {"template": "helpfulness"},
            "calibration_runs": 1,
        },
    )

    assert result.score is None
    assert result.error == "judge_failure_permanent"
    assert result.extra["failure_classification"] == "permanent"


@pytest.mark.asyncio
async def test_llm_judge_resolve_criteria_supports_multiple_payload_shapes() -> None:
    scorer = LLMJudgeScorer(settings=make_settings())

    with pytest.raises(ValueError, match="rubric_service"):
        await scorer._resolve_criteria_from_config({"rubric_id": str(uuid4())}, "judge-v1")

    model_dump_rubric = SimpleNamespace(
        model_dump=lambda mode="json": {
            "id": str(uuid4()),
            "version": 7,
            "name": "dumped",
            "criteria": [
                {"name": "accuracy", "description": "desc", "scale": 5},
            ],
        }
    )
    scorer.rubric_service = SimpleNamespace(
        get_rubric_model=AsyncMock(return_value=model_dump_rubric)
    )
    criteria, metadata = await scorer._resolve_criteria_from_config(
        {"rubric_id": str(uuid4())},
        "judge-v1",
    )

    assert criteria[0]["name"] == "accuracy"
    assert metadata["rubric_name"] == "dumped"

    scorer.rubric_service = SimpleNamespace(
        get_rubric_model=AsyncMock(
            return_value={
                "id": str(uuid4()),
                "version": 9,
                "name": "dict-rubric",
                "criteria": [{"name": "helpfulness", "description": "desc", "scale": 5}],
            }
        )
    )
    _, metadata = await scorer._resolve_criteria_from_config(
        {"rubric_id": str(uuid4())},
        "judge-v1",
    )
    assert metadata["rubric_name"] == "dict-rubric"


@pytest.mark.asyncio
async def test_llm_judge_heuristic_and_exception_helpers() -> None:
    scorer = LLMJudgeScorer(settings=make_settings())
    heuristic = await scorer._judge_with_retries(
        actual="same",
        expected="same",
        judge_model="judge-v1",
        criteria=[{"name": "accuracy", "description": "desc", "scale": 5}],
    )

    assert heuristic["score"] == 5.0
    assert scorer._resolve_criteria(None) == []
    assert scorer._classify_exception(ValueError("bad")) == "permanent"
    assert (
        scorer._criterion_to_dict({"name": "accuracy", "description": "desc", "scale": 5})["name"]
        == "accuracy"
    )
    with pytest.raises(ValueError, match="Unsupported"):
        scorer._criterion_to_dict(object())
