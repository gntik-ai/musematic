from __future__ import annotations

import json
from collections import Counter
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import NotFoundError, ValidationError
from platform.common.tracing import traced_async
from platform.evaluation.models import BenchmarkCase, EvalSetStatus
from platform.evaluation.repository import EvaluationRepository
from platform.testing.adversarial_service import AdversarialGenerationService
from platform.testing.events import (
    SuiteGeneratedPayload,
    TestingEventType,
    publish_testing_event,
)
from platform.testing.models import GeneratedTestSuite, SuiteType
from platform.testing.repository import TestingRepository
from platform.testing.schemas import (
    AdversarialCaseListResponse,
    AdversarialCaseResponse,
    GeneratedTestSuiteListResponse,
    GeneratedTestSuiteResponse,
    GenerateSuiteRequest,
    ImportSuiteResponse,
)
from typing import Any
from uuid import UUID


class TestSuiteGenerationService:
    def __init__(
        self,
        *,
        repository: TestingRepository,
        evaluation_repository: EvaluationRepository,
        settings: Any,
        producer: EventProducer | None,
        object_storage: Any,
        adversarial_service: AdversarialGenerationService,
    ) -> None:
        self.repository = repository
        self.evaluation_repository = evaluation_repository
        self.settings = settings
        self.producer = producer
        self.object_storage = object_storage
        self.adversarial_service = adversarial_service

    @traced_async("testing.suite_generation.start_generation")
    async def start_generation(self, payload: GenerateSuiteRequest) -> GeneratedTestSuiteResponse:
        version = await self.repository.get_next_suite_version(
            workspace_id=payload.workspace_id,
            agent_fqn=payload.agent_fqn,
            suite_type=payload.suite_type,
        )
        suite = await self.repository.create_suite(
            GeneratedTestSuite(
                workspace_id=payload.workspace_id,
                agent_fqn=payload.agent_fqn,
                agent_id=payload.agent_id,
                suite_type=payload.suite_type,
                version=version,
                case_count=0,
                category_counts={},
            )
        )
        await self._commit()
        return GeneratedTestSuiteResponse.model_validate(suite)

    @traced_async("testing.suite_generation.generate_suite")
    async def generate_suite(
        self,
        suite_id: UUID,
        *,
        cases_per_category: int,
    ) -> GeneratedTestSuiteResponse:
        suite = await self.repository.get_suite(suite_id)
        if suite is None:
            raise NotFoundError("TEST_SUITE_NOT_FOUND", "Generated suite not found")
        if suite.case_count > 0:
            return GeneratedTestSuiteResponse.model_validate(suite)
        cases = await self.adversarial_service.generate_cases(
            suite,
            cases_per_category=cases_per_category,
        )
        category_counts = Counter(case.category.value for case in cases)
        artifact_key: str | None = None
        if len(cases) > 500:
            artifact_key = await self._archive_suite(suite.id, cases)
        await self.repository.update_suite(
            suite,
            case_count=len(cases),
            category_counts=dict(category_counts),
            artifact_key=artifact_key,
        )
        await self._commit()
        await publish_testing_event(
            self.producer,
            TestingEventType.suite_generated,
            SuiteGeneratedPayload(
                suite_id=suite.id,
                workspace_id=suite.workspace_id,
                agent_fqn=suite.agent_fqn,
                suite_type=suite.suite_type.value,
                case_count=len(cases),
            ),
            CorrelationContext(
                correlation_id=suite.id,
                workspace_id=suite.workspace_id,
            ),
        )
        return GeneratedTestSuiteResponse.model_validate(suite)

    @traced_async("testing.suite_generation.list_suites")
    async def list_suites(
        self,
        *,
        workspace_id: UUID,
        agent_fqn: str | None,
        suite_type: SuiteType | None,
        page: int,
        page_size: int,
    ) -> GeneratedTestSuiteListResponse:
        items, total = await self.repository.list_suites(
            workspace_id,
            agent_fqn=agent_fqn,
            suite_type=suite_type,
            page=page,
            page_size=page_size,
        )
        return GeneratedTestSuiteListResponse(
            items=[GeneratedTestSuiteResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @traced_async("testing.suite_generation.get_suite")
    async def get_suite(
        self,
        suite_id: UUID,
        workspace_id: UUID | None = None,
    ) -> GeneratedTestSuiteResponse:
        suite = await self.repository.get_suite(suite_id, workspace_id)
        if suite is None:
            raise NotFoundError("TEST_SUITE_NOT_FOUND", "Generated suite not found")
        return GeneratedTestSuiteResponse.model_validate(suite)

    @traced_async("testing.suite_generation.list_cases")
    async def list_cases(
        self,
        *,
        suite_id: UUID,
        category: Any | None,
        page: int,
        page_size: int,
    ) -> AdversarialCaseListResponse:
        items, total = await self.repository.list_adversarial_cases(
            suite_id,
            category=category,
            page=page,
            page_size=page_size,
        )
        return AdversarialCaseListResponse(
            items=[AdversarialCaseResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @traced_async("testing.suite_generation.import_to_eval_set")
    async def import_to_eval_set(self, suite_id: UUID, eval_set_id: UUID) -> ImportSuiteResponse:
        suite = await self.repository.get_suite(suite_id)
        if suite is None:
            raise NotFoundError("TEST_SUITE_NOT_FOUND", "Generated suite not found")
        eval_set = await self.evaluation_repository.get_eval_set(eval_set_id, suite.workspace_id)
        if eval_set is None:
            raise NotFoundError("EVAL_SET_NOT_FOUND", "Evaluation set not found")
        if eval_set.status is EvalSetStatus.archived:
            raise ValidationError("EVAL_SET_ARCHIVED", "Cannot import into an archived eval set")
        cases, _ = await self.repository.list_adversarial_cases(
            suite.id,
            category=None,
            page=1,
            page_size=max(1, suite.case_count or 1000),
        )
        position = await self.evaluation_repository.get_next_case_position(eval_set_id)
        for offset, case in enumerate(cases):
            await self.evaluation_repository.create_benchmark_case(
                BenchmarkCase(
                    eval_set_id=eval_set_id,
                    input_data=dict(case.input_data),
                    expected_output=case.expected_behavior,
                    scoring_criteria={},
                    metadata_tags={
                        "generated_suite_id": str(suite.id),
                        "suite_type": suite.suite_type.value,
                        "adversarial_category": case.category.value,
                    },
                    category=case.category.value,
                    position=position + offset,
                )
            )
        await self.repository.update_suite(suite, imported_into_eval_set_id=eval_set_id)
        await self._commit()
        return ImportSuiteResponse(imported_case_count=len(cases), eval_set_id=eval_set_id)

    @traced_async("testing.suite_generation.archive_suite")
    async def _archive_suite(self, suite_id: UUID, cases: list[Any]) -> str:
        bucket = "evaluation-generated-suites"
        artifact_key = f"{suite_id}/suite.json"
        await self.object_storage.create_bucket_if_not_exists(bucket)
        payload = [
            {
                "id": str(case.id),
                "category": case.category.value,
                "input_data": dict(case.input_data),
                "expected_behavior": case.expected_behavior,
                "generation_prompt_hash": case.generation_prompt_hash,
            }
            for case in cases
        ]
        await self.object_storage.upload_object(
            bucket,
            artifact_key,
            json.dumps(payload, default=str).encode("utf-8"),
            content_type="application/json",
        )
        return artifact_key

    @traced_async("testing.suite_generation.commit")
    async def _commit(self) -> None:
        await self.repository.session.commit()
