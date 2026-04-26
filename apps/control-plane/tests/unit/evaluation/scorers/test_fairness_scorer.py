from __future__ import annotations

from platform.evaluation.schemas import FairnessCase, FairnessRunRequest, FairnessScorerConfig
from platform.evaluation.scorers.fairness import FairnessScorer
from platform.evaluation.service import FairnessEvaluationService
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

AGENT_ID = UUID("00000000-0000-0000-0000-000000000101")
SUITE_ID = UUID("00000000-0000-0000-0000-000000000202")
RUN_ID = UUID("00000000-0000-0000-0000-000000000303")


def _cases(*, include_scores: bool = True) -> list[FairnessCase]:
    rows = [
        ("positive", "positive", "en", 0.9),
        ("negative", "positive", "en", 0.4),
        ("positive", "positive", "es", 0.8),
        ("positive", "negative", "es", 0.7),
    ]
    return [
        FairnessCase(
            prediction=prediction,
            label=label,
            score=score if include_scores else None,
            group_attributes={"lang": lang},
        )
        for prediction, label, lang, score in rows
    ]


async def _score(
    cases: list[FairnessCase],
    config: FairnessScorerConfig,
    *,
    run_id: UUID = RUN_ID,
):
    return await FairnessScorer().score_suite(
        evaluation_run_id=run_id,
        agent_id=AGENT_ID,
        agent_revision_id="rev-1",
        suite_id=SUITE_ID,
        cases=cases,
        config=config,
    )


@pytest.mark.asyncio
async def test_score_suite_is_deterministic_for_same_input() -> None:
    config = FairnessScorerConfig(
        metrics=["demographic_parity", "equal_opportunity", "calibration"],
        group_attributes=["lang"],
        min_group_size=1,
        fairness_band=0.6,
    )

    first = await _score(_cases(), config)
    second = await _score(_cases(), config)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert len(first.rows) == 3
    assert first.overall_passed is True


@pytest.mark.asyncio
async def test_missing_and_below_min_groups_are_reported_in_coverage() -> None:
    cases = [
        *_cases(),
        FairnessCase(prediction="positive", label="positive", group_attributes={}),
        FairnessCase(
            prediction="positive",
            label="positive",
            score=0.6,
            group_attributes={"lang": "nb"},
        ),
    ]
    config = FairnessScorerConfig(
        metrics=["demographic_parity"],
        group_attributes=["lang"],
        min_group_size=2,
    )

    result = await _score(cases, config)

    coverage = result.coverage["lang"]
    assert coverage["missing"] == 1
    assert coverage["excluded_below_min_size"] == {"nb": 1}
    assert result.rows[0].per_group_scores == {"en": 0.5, "es": 1.0}


@pytest.mark.asyncio
async def test_single_group_adds_note_and_omits_metric_row() -> None:
    config = FairnessScorerConfig(
        metrics=["demographic_parity"],
        group_attributes=["lang"],
        min_group_size=1,
    )
    cases = [
        FairnessCase(prediction="positive", label="positive", group_attributes={"lang": "en"}),
        FairnessCase(prediction="negative", label="negative", group_attributes={"lang": "en"}),
    ]

    result = await _score(cases, config)

    assert result.rows == []
    assert result.overall_passed is False
    assert result.notes == ["demographic_parity:lang:insufficient_groups"]


@pytest.mark.asyncio
async def test_calibration_without_probabilities_is_not_fatal() -> None:
    config = FairnessScorerConfig(
        metrics=["demographic_parity", "calibration"],
        group_attributes=["lang"],
        min_group_size=2,
    )

    result = await _score(_cases(include_scores=False), config)

    assert [row.metric_name for row in result.rows] == ["demographic_parity"]
    assert result.notes == [
        "calibration:lang:unsupported:calibration requires probabilistic score output"
    ]


@pytest.mark.asyncio
async def test_metric_passed_depends_on_fairness_band() -> None:
    narrow = await _score(
        _cases(),
        FairnessScorerConfig(
            metrics=["demographic_parity"],
            group_attributes=["lang"],
            min_group_size=2,
            fairness_band=0.4,
        ),
    )
    wide = await _score(
        _cases(),
        FairnessScorerConfig(
            metrics=["demographic_parity"],
            group_attributes=["lang"],
            min_group_size=2,
            fairness_band=0.6,
        ),
    )

    assert narrow.rows[0].spread == 0.5
    assert narrow.rows[0].passed is False
    assert wide.rows[0].passed is True


class FakeSession:
    async def execute(self, *_args: object, **_kwargs: object) -> None:
        return None

    async def commit(self) -> None:
        return None


class FakeFairnessRepository:
    session = FakeSession()

    def __init__(self) -> None:
        self.rows: list[object] = []

    async def insert_fairness_evaluation_rows(self, rows: list[object]) -> list[object]:
        self.rows.extend(rows)
        return rows


@pytest.mark.asyncio
async def test_service_audits_metric_without_group_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audits: list[dict[str, Any]] = []

    async def fake_audit_hook(
        _service: object,
        _audit_event_id: object,
        _source: str,
        payload: dict[str, Any],
    ) -> None:
        audits.append(payload)

    monkeypatch.setattr(
        "platform.evaluation.service.AuditChainService",
        lambda *_args, **_kw: object(),
    )
    monkeypatch.setattr("platform.evaluation.service.audit_chain_hook", fake_audit_hook)
    service = FairnessEvaluationService(
        repository=FakeFairnessRepository(),  # type: ignore[arg-type]
        settings=SimpleNamespace(audit=SimpleNamespace()),
        producer=None,
    )

    await service.run_fairness_evaluation(
        FairnessRunRequest(
            workspace_id=uuid4(),
            agent_id=AGENT_ID,
            agent_revision_id="rev-1",
            suite_id=SUITE_ID,
            cases=_cases(),
            config=FairnessScorerConfig(
                metrics=["demographic_parity"],
                group_attributes=["lang"],
                min_group_size=2,
            ),
        )
    )

    assert audits
    assert audits[0]["group_attribute"] == "lang"
    assert "per_group_scores" not in audits[0]
    assert all(value not in {"en", "es"} for value in audits[0].values())
