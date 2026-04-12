from __future__ import annotations

from platform.common.events.producer import EventProducer
from platform.common.exceptions import NotFoundError
from platform.common.tracing import traced_async
from platform.evaluation.scorers.llm_judge import LLMJudgeScorer
from platform.fleets.repository import FleetMemberRepository, FleetRepository
from platform.testing.models import CoordinationTestResult
from platform.testing.repository import TestingRepository
from typing import Any
from uuid import UUID


class CoordinationTestService:
    def __init__(
        self,
        *,
        repository: TestingRepository,
        fleet_repository: FleetRepository,
        member_repository: FleetMemberRepository,
        execution_query: Any,
        producer: EventProducer | None = None,
        llm_judge: LLMJudgeScorer | None = None,
    ) -> None:
        self.repository = repository
        self.fleet_repository = fleet_repository
        self.member_repository = member_repository
        self.execution_query = execution_query
        self.producer = producer
        self.llm_judge = llm_judge or LLMJudgeScorer()

    @traced_async("testing.coordination.run_coordination_test")
    async def run_coordination_test(
        self,
        fleet_id: UUID,
        execution_id: UUID,
        workspace_id: UUID,
    ) -> CoordinationTestResult:
        fleet = await self.fleet_repository.get_by_id(fleet_id, workspace_id)
        if fleet is None:
            raise NotFoundError("FLEET_NOT_FOUND", "Fleet not found")
        members = await self.member_repository.get_by_fleet(fleet_id)
        if len(members) < 2:
            result = await self.repository.create_coordination_result(
                CoordinationTestResult(
                    workspace_id=workspace_id,
                    fleet_id=fleet_id,
                    execution_id=execution_id,
                    completion_score=0.0,
                    coherence_score=0.0,
                    goal_achievement_score=0.0,
                    overall_score=0.0,
                    per_agent_scores={},
                    insufficient_members=True,
                )
            )
            await self.repository.session.commit()
            return result
        journal = await self.execution_query.get_journal(execution_id)
        events = list(getattr(journal, "items", journal))
        completed_steps = {
            str(getattr(event, "step_id", "") or "")
            for event in events
            if str(getattr(event, "event_type", "")) == "completed"
            and getattr(event, "step_id", None) is not None
        }
        all_steps = {
            str(getattr(event, "step_id", "") or "")
            for event in events
            if getattr(event, "step_id", None) is not None
        }
        completion_score = len(completed_steps) / max(1, len(all_steps))
        communication_payloads = [
            self._event_payload(event)
            for event in events
            if "message" in str(getattr(event, "event_type", ""))
            or self._event_payload(event).get("message") is not None
        ]
        communication_values = [
            str(payload.get("message") or payload.get("content") or payload)
            for payload in communication_payloads
        ]
        unique_messages = {value.strip() for value in communication_values if value.strip()}
        coherence_score = (
            len(unique_messages) / max(1, len(communication_values))
            if communication_values
            else 1.0
        )
        outputs = [
            str(
                self._event_payload(event).get("output")
                or self._event_payload(event).get("result")
                or ""
            ).strip()
            for event in events
            if str(getattr(event, "event_type", "")) == "completed"
        ]
        collective_output = "\n".join(item for item in outputs if item)
        judge = await self.llm_judge.score(
            collective_output or "execution completed",
            "Fleet members coordinate to complete the workflow without redundancy.",
            {
                "judge_model": "heuristic-judge",
                "rubric": {"template": "helpfulness"},
                "calibration_runs": 1,
            },
        )
        goal_achievement_score = self._normalize_judge_score(judge.score, judge.extra)
        per_agent_scores = self._per_agent_scores(members, events)
        overall_score = (
            completion_score + coherence_score + goal_achievement_score
        ) / 3.0
        result = await self.repository.create_coordination_result(
            CoordinationTestResult(
                workspace_id=workspace_id,
                fleet_id=fleet_id,
                execution_id=execution_id,
                completion_score=completion_score,
                coherence_score=coherence_score,
                goal_achievement_score=goal_achievement_score,
                overall_score=overall_score,
                per_agent_scores=per_agent_scores,
                insufficient_members=False,
            )
        )
        await self.repository.session.commit()
        return result

    @staticmethod
    def _event_payload(event: Any) -> dict[str, Any]:
        payload = getattr(event, "payload", {})
        return dict(payload) if isinstance(payload, dict) else {}

    @staticmethod
    def _normalize_judge_score(score: float | None, extra: dict[str, Any]) -> float:
        if score is None:
            return 0.0
        max_scale = float(extra.get("max_scale", 5.0) or 5.0)
        return max(0.0, min(1.0, float(score) / max(max_scale, 1.0)))

    @staticmethod
    def _per_agent_scores(members: list[Any], events: list[Any]) -> dict[str, Any]:
        per_agent: dict[str, dict[str, float | int]] = {}
        for member in members:
            agent_fqn = str(getattr(member, "agent_fqn", "") or "")
            relevant = [
                event
                for event in events
                if str(getattr(event, "agent_fqn", "") or "") == agent_fqn
            ]
            total_steps = sum(
                1
                for event in relevant
                if getattr(event, "step_id", None) is not None
            )
            completed_steps = sum(
                1
                for event in relevant
                if str(getattr(event, "event_type", "")) == "completed"
            )
            per_agent[agent_fqn] = {
                "event_count": len(relevant),
                "completed_steps": completed_steps,
                "completion_ratio": completed_steps / max(1, total_steps),
            }
        return per_agent
