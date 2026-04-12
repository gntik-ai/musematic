from __future__ import annotations

from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import NotFoundError, ValidationError
from platform.common.tracing import traced_async
from platform.evaluation.events import (
    EvaluationEventType,
    HumanGradeSubmittedPayload,
    publish_evaluation_event,
)
from platform.evaluation.models import HumanAiGrade, ReviewDecision
from platform.evaluation.repository import EvaluationRepository
from platform.evaluation.schemas import (
    HumanAiGradeResponse,
    HumanGradeSubmit,
    HumanGradeUpdate,
    ReviewProgressResponse,
)
from uuid import UUID, uuid4


class HumanGradingService:
    def __init__(
        self,
        *,
        repository: EvaluationRepository,
        producer: EventProducer | None = None,
    ) -> None:
        self.repository = repository
        self.producer = producer

    @traced_async("evaluation.human_grading.submit_grade")
    async def submit_grade(
        self,
        verdict_id: UUID,
        reviewer_id: UUID,
        payload: HumanGradeSubmit,
    ) -> HumanAiGradeResponse:
        verdict = await self.repository.get_verdict(verdict_id)
        if verdict is None:
            raise NotFoundError("EVALUATION_VERDICT_NOT_FOUND", "Evaluation verdict not found")
        existing = await self.repository.get_human_grade_by_verdict(verdict_id)
        if existing is not None:
            raise ValidationError("GRADE_ALREADY_EXISTS", "Use PATCH to update the existing grade")
        if payload.decision is ReviewDecision.overridden and payload.override_score is None:
            raise ValidationError(
                "OVERRIDE_SCORE_REQUIRED",
                "override_score is required when overriding",
            )
        grade = await self.repository.create_human_grade(
            HumanAiGrade(
                verdict_id=verdict_id,
                reviewer_id=reviewer_id,
                decision=payload.decision,
                override_score=payload.override_score,
                feedback=payload.feedback,
                original_score=verdict.overall_score or 0.0,
                reviewed_at=datetime.now(UTC),
            )
        )
        await self._commit()
        if verdict.run is None:
            raise ValidationError(
                "EVALUATION_RUN_NOT_LOADED",
                "Evaluation run context is required for human grading events",
            )
        workspace_id = verdict.run.workspace_id
        correlation = CorrelationContext(
            correlation_id=uuid4(),
            workspace_id=workspace_id,
        )
        await publish_evaluation_event(
            self.producer,
            EvaluationEventType.human_grade_submitted,
            HumanGradeSubmittedPayload(
                grade_id=grade.id,
                verdict_id=verdict.id,
                workspace_id=workspace_id,
                decision=grade.decision.value,
            ),
            correlation,
        )
        return HumanAiGradeResponse.model_validate(grade)

    @traced_async("evaluation.human_grading.update_grade")
    async def update_grade(self, grade_id: UUID, payload: HumanGradeUpdate) -> HumanAiGradeResponse:
        grade = await self.repository.get_human_grade(grade_id)
        if grade is None:
            raise NotFoundError("HUMAN_GRADE_NOT_FOUND", "Human grade not found")
        if grade.decision is ReviewDecision.overridden and payload.override_score is None:
            raise ValidationError(
                "OVERRIDE_SCORE_REQUIRED",
                "override_score is required for overridden grades",
            )
        updated = await self.repository.update_human_grade(
            grade,
            decision=grade.decision,
            override_score=(
                payload.override_score
                if payload.override_score is not None
                else grade.override_score
            ),
            feedback=payload.feedback if payload.feedback is not None else grade.feedback,
            reviewed_at=datetime.now(UTC),
        )
        await self._commit()
        return HumanAiGradeResponse.model_validate(updated)

    @traced_async("evaluation.human_grading.get_grade_for_verdict")
    async def get_grade_for_verdict(self, verdict_id: UUID) -> HumanAiGradeResponse:
        grade = await self.repository.get_human_grade_by_verdict(verdict_id)
        if grade is None:
            raise NotFoundError("HUMAN_GRADE_NOT_FOUND", "Human grade not found")
        return HumanAiGradeResponse.model_validate(grade)

    @traced_async("evaluation.human_grading.get_review_progress")
    async def get_review_progress(self, run_id: UUID) -> ReviewProgressResponse:
        progress = await self.repository.get_review_progress(run_id)
        return ReviewProgressResponse(**progress)

    @traced_async("evaluation.human_grading.commit")
    async def _commit(self) -> None:
        await self.repository.session.commit()
