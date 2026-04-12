from __future__ import annotations

from platform.trust.schemas import PrivacyAssessmentRequest, PrivacyAssessmentResponse
from typing import Any


class PrivacyAssessmentService:
    def __init__(self, *, policy_engine: Any | None) -> None:
        self.policy_engine = policy_engine

    async def assess(self, request: PrivacyAssessmentRequest) -> PrivacyAssessmentResponse:
        checker = getattr(self.policy_engine, "check_privacy_compliance", None)
        if checker is None:
            return PrivacyAssessmentResponse(compliant=True, blocked=False, violations=[])
        result = await checker(
            context_assembly_id=request.context_assembly_id,
            workspace_id=request.workspace_id,
        )
        if isinstance(result, dict):
            violations = result.get("violations", [])
            compliant = bool(result.get("compliant", not violations))
            blocked = bool(result.get("blocked", not compliant))
            return PrivacyAssessmentResponse(
                compliant=compliant,
                blocked=blocked,
                violations=[dict(item) for item in violations if isinstance(item, dict)],
            )
        return PrivacyAssessmentResponse(
            compliant=bool(result), blocked=not bool(result), violations=[]
        )
