from __future__ import annotations

from platform.evaluation.schemas import FairnessCase, FairnessRunRequest, FairnessScorerConfig
from platform.evaluation.service import FairnessEvaluationService
from types import SimpleNamespace
from uuid import uuid4

import pytest


class FakeSession:
    async def commit(self) -> None:
        return None


class FakeFairnessRepository:
    session = FakeSession()

    def __init__(self) -> None:
        self.rows: list[object] = []

    async def insert_fairness_evaluation_rows(self, rows: list[object]) -> list[object]:
        self.rows.extend(rows)
        return rows

    async def get_fairness_evaluation_run(self, evaluation_run_id):
        return [row for row in self.rows if row.evaluation_run_id == evaluation_run_id]


def _cases() -> list[FairnessCase]:
    cases: list[FairnessCase] = []
    for index in range(100):
        lang = "en" if index < 50 else "es"
        prediction = "positive" if index % 3 else "negative"
        label = "positive" if index % 4 else "negative"
        score = 0.8 if prediction == "positive" else 0.2
        cases.append(
            FairnessCase(
                id=str(index),
                prediction=prediction,
                label=label,
                score=score,
                group_attributes={"lang": lang},
            )
        )
    return cases


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fairness_evaluation_persists_rows_and_is_deterministic() -> None:
    repository = FakeFairnessRepository()
    service = FairnessEvaluationService(
        repository=repository,  # type: ignore[arg-type]
        settings=SimpleNamespace(),
        producer=None,
    )
    request = FairnessRunRequest(
        workspace_id=uuid4(),
        agent_id=uuid4(),
        agent_revision_id="rev-1",
        suite_id=uuid4(),
        cases=_cases(),
        config=FairnessScorerConfig(
            metrics=["demographic_parity", "equal_opportunity", "calibration"],
            group_attributes=["lang"],
            min_group_size=5,
            fairness_band=0.25,
        ),
    )

    first = await service.run_fairness_evaluation(request)
    second = await service.run_fairness_evaluation(request)

    assert len(repository.rows) == 6
    assert len(first.rows) == 3
    first_rows = [
        row.model_dump(mode="json", exclude={"evaluation_run_id"}) for row in first.rows
    ]
    second_rows = [
        row.model_dump(mode="json", exclude={"evaluation_run_id"}) for row in second.rows
    ]
    assert first_rows == second_rows
    assert all(row.coverage["included"] == {"en": 50, "es": 50} for row in first.rows)
