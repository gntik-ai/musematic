from __future__ import annotations

import sys
import types

if "jsonschema" not in sys.modules:
    jsonschema_stub = types.ModuleType("jsonschema")

    class _ValidationError(Exception):
        pass

    def _validate(*, instance: object, schema: dict[str, object]) -> None:
        del instance, schema
        return None

    jsonschema_stub.ValidationError = _ValidationError
    jsonschema_stub.validate = _validate
    sys.modules["jsonschema"] = jsonschema_stub

from platform.common.exceptions import AuthorizationError, NotFoundError, ValidationError
from platform.evaluation.models import EvalSetStatus
from platform.testing.adversarial_service import AdversarialGenerationService
from platform.testing.coordination_service import CoordinationTestService
from platform.testing.dependencies import (
    build_adversarial_generation_service,
    build_coordination_service,
    build_drift_service,
    build_test_suite_generation_service,
    get_adversarial_generation_service,
    get_coordination_service,
    get_drift_service,
    get_test_suite_generation_service,
)
from platform.testing.drift_service import DriftDetectionService
from platform.testing.models import AdversarialCategory, SuiteType
from platform.testing.router import (
    _actor_id,
    _generate_suite_background,
    _require_roles,
    _workspace_id,
    acknowledge_drift_alert,
    generate_suite,
    get_coordination_test,
    get_suite,
    import_suite,
    list_drift_alerts,
    list_suite_cases,
    list_suites,
    run_coordination_test,
)
from platform.testing.schemas import (
    AdversarialCaseListResponse,
    CoordinationTestRequest,
    CoordinationTestResultResponse,
    DriftAlertListResponse,
    DriftAlertResponse,
    GeneratedTestSuiteListResponse,
    GeneratedTestSuiteResponse,
    GenerateSuiteRequest,
    ImportSuiteRequest,
    ImportSuiteResponse,
    _clean_optional_text,
)
from platform.testing.service_interfaces import CoordinationTestServiceInterface
from platform.testing.suite_generation_service import TestSuiteGenerationService
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import BackgroundTasks, FastAPI

from tests.evaluation_testing_support import (
    ClickHouseStub,
    ExecutionQueryStub,
    ObjectStorageStub,
    RegistryServiceStub,
    SessionStub,
    build_adversarial_case,
    build_coordination_result,
    build_drift_alert,
    build_eval_set,
    build_suite,
    make_request,
    make_settings,
)


def _apply_updates(model: object, **fields: object) -> object:
    for key, value in fields.items():
        setattr(model, key, value)
    return model


def _persist_alert(alert: object) -> object:
    if getattr(alert, "id", None) is None:
        alert.id = uuid4()
    if getattr(alert, "created_at", None) is None:
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        alert.created_at = now
        alert.updated_at = now
    return alert


def _acknowledge_alert(model: object, **fields: object) -> object:
    model.acknowledged = True
    return _apply_updates(model, **fields)


def _admin_user(workspace_id: UUID) -> dict[str, object]:
    return {
        "sub": str(uuid4()),
        "workspace_id": str(workspace_id),
        "roles": [{"role": "workspace_admin"}],
    }


@pytest.mark.asyncio
async def test_adversarial_generation_service_covers_registry_provider_and_fallback_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    suite = build_suite(workspace_id=workspace_id)
    repo = SimpleNamespace(create_adversarial_cases=AsyncMock(side_effect=lambda cases: cases))
    service = AdversarialGenerationService(
        repository=repo,
        settings=make_settings(),
        registry_service=RegistryServiceStub(
            profile={
                "purpose": "finance assistant",
                "approach": "deterministic",
                "tags": ["finance"],
                "role_types": ["executor"],
            }
        ),
    )
    provider_calls = {"count": 0}

    async def _provider_cases(prompt: str) -> list[dict[str, object]]:
        provider_calls["count"] += 1
        del prompt
        return [
            {
                "input_data": {"prompt": "from provider"},
                "expected_behavior": "refuse",
            }
        ]

    monkeypatch.setattr(service, "_fetch_provider_cases", _provider_cases)
    created = await service.generate_cases(suite, cases_per_category=1)
    default_profile = await AdversarialGenerationService(
        repository=repo,
        settings=make_settings(),
        registry_service=None,
    )._get_agent_profile(workspace_id, suite.agent_fqn)

    assert len(created) == len(AdversarialCategory)
    assert provider_calls["count"] == len(AdversarialCategory)
    assert created[0].generation_prompt_hash
    assert "finance assistant" in service._build_prompt(
        {"purpose": "finance assistant", "approach": "strict", "tags": [], "role_types": []},
        suite.agent_fqn,
        AdversarialCategory.prompt_injection,
        1,
    )
    assert default_profile["purpose"] == "general assistant"
    assert (
        AdversarialGenerationService._fallback_case(
            suite.agent_fqn,
            AdversarialCategory.resource_exhaustion,
            0,
        )["expected_behavior"]
        == "apply_resource_limits_and_degrade_gracefully"
    )


@pytest.mark.asyncio
async def test_test_suite_generation_service_and_drift_detection_cover_main_paths() -> None:
    workspace_id = uuid4()
    suite = build_suite(workspace_id=workspace_id)
    case = build_adversarial_case(suite_id=suite.id)
    eval_set = build_eval_set(workspace_id=workspace_id)
    repo = SimpleNamespace(
        session=SessionStub(),
        get_next_suite_version=AsyncMock(return_value=1),
        create_suite=AsyncMock(return_value=suite),
        get_suite=AsyncMock(side_effect=[suite, suite, suite, suite]),
        update_suite=AsyncMock(side_effect=lambda model, **fields: _apply_updates(model, **fields)),
        list_suites=AsyncMock(return_value=([suite], 1)),
        list_adversarial_cases=AsyncMock(return_value=([case], 1)),
        list_drift_alerts=AsyncMock(
            return_value=([build_drift_alert(workspace_id=workspace_id)], 1)
        ),
        get_drift_alert=AsyncMock(return_value=build_drift_alert(workspace_id=workspace_id)),
        acknowledge_drift_alert=AsyncMock(side_effect=_acknowledge_alert),
        create_drift_alert=AsyncMock(side_effect=_persist_alert),
    )
    evaluation_repo = SimpleNamespace(
        get_eval_set=AsyncMock(return_value=eval_set),
        get_next_case_position=AsyncMock(return_value=2),
        create_benchmark_case=AsyncMock(side_effect=lambda benchmark_case: benchmark_case),
        list_active_robustness_runs_by_agent=AsyncMock(return_value=[]),
    )
    adversarial_service = SimpleNamespace(generate_cases=AsyncMock(return_value=[case] * 2))
    object_storage = ObjectStorageStub()
    suite_service = TestSuiteGenerationService(
        repository=repo,
        evaluation_repository=evaluation_repo,
        settings=make_settings(),
        producer=None,
        object_storage=object_storage,
        adversarial_service=adversarial_service,
    )
    started = await suite_service.start_generation(
        GenerateSuiteRequest(
            workspace_id=workspace_id,
            agent_fqn=suite.agent_fqn,
            agent_id=suite.agent_id,
            suite_type=SuiteType.adversarial,
            cases_per_category=2,
        )
    )
    generated = await suite_service.generate_suite(suite.id, cases_per_category=2)
    listed = await suite_service.list_suites(
        workspace_id=workspace_id,
        agent_fqn=suite.agent_fqn,
        suite_type=suite.suite_type,
        page=1,
        page_size=10,
    )
    fetched = await suite_service.get_suite(suite.id, workspace_id)
    listed_cases = await suite_service.list_cases(
        suite_id=suite.id,
        category=None,
        page=1,
        page_size=10,
    )
    imported = await suite_service.import_to_eval_set(suite.id, eval_set.id)
    archived = await suite_service._archive_suite(suite.id, [case] * 501)

    clickhouse = ClickHouseStub()
    clickhouse.query_results.extend(
        [
            [
                {
                    "baseline_value": 0.9,
                    "stddev_value": 0.1,
                    "latest_measured_at": "now",
                }
            ],
            [{"score": 0.5, "run_id": str(uuid4())}],
            [
                {
                    "workspace_id": str(workspace_id),
                    "agent_fqn": suite.agent_fqn,
                    "eval_set_id": str(eval_set.id),
                }
            ],
            [
                {
                    "baseline_value": 0.9,
                    "stddev_value": 0.1,
                    "latest_measured_at": "now",
                }
            ],
            [{"score": 0.5, "run_id": str(uuid4())}],
        ]
    )
    drift_service = DriftDetectionService(
        repository=repo,
        evaluation_repository=evaluation_repo,
        clickhouse_client=clickhouse,
        settings=make_settings(),
        producer=None,
    )
    await drift_service.ensure_schema()
    await drift_service.record_eval_metric(
        run_id=uuid4(),
        agent_fqn=suite.agent_fqn,
        eval_set_id=eval_set.id,
        score=0.5,
        workspace_id=workspace_id,
    )
    alert = await drift_service.detect_drift(suite.agent_fqn, eval_set.id, workspace_id)
    listed_alerts = await drift_service.list_alerts(
        workspace_id=workspace_id,
        agent_fqn=suite.agent_fqn,
        eval_set_id=eval_set.id,
        acknowledged=False,
        page=1,
        page_size=10,
    )
    acknowledged = await drift_service.acknowledge_alert(
        repo.get_drift_alert.return_value.id, uuid4()
    )
    scanned = await drift_service.run_drift_scan_all()

    assert started.id == suite.id
    assert generated.case_count == 2
    assert listed.total == 1
    assert fetched.id == suite.id
    assert listed_cases.total == 1
    assert imported.imported_case_count == 1
    assert archived.endswith("/suite.json")
    assert clickhouse.commands
    assert clickhouse.inserts[0][0] == "testing_drift_metrics"
    assert alert is not None
    assert listed_alerts.total == 1
    assert acknowledged.acknowledged is True
    assert len(scanned) == 1


@pytest.mark.asyncio
async def test_drift_detection_service_early_returns_and_coordination_service_paths() -> None:
    workspace_id = uuid4()
    fleet_id = uuid4()
    execution_id = uuid4()
    repo = SimpleNamespace(
        session=SessionStub(),
        create_coordination_result=AsyncMock(side_effect=lambda row: row),
    )
    fleet_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(id=fleet_id)))
    members = [SimpleNamespace(agent_fqn="one"), SimpleNamespace(agent_fqn="two")]
    member_repo = SimpleNamespace(
        get_by_fleet=AsyncMock(
            side_effect=[
                [SimpleNamespace(agent_fqn="one")],
                members,
            ]
        )
    )
    llm_judge = SimpleNamespace(
        score=AsyncMock(return_value=SimpleNamespace(score=4.0, extra={"max_scale": 5.0}))
    )
    execution_query = ExecutionQueryStub(
        journal_items=[
            SimpleNamespace(
                event_type="completed", step_id="s1", agent_fqn="one", payload={"output": "done"}
            ),
            SimpleNamespace(
                event_type="message.sent", step_id="s1", agent_fqn="one", payload={"message": "hi"}
            ),
            SimpleNamespace(
                event_type="completed",
                step_id="s2",
                agent_fqn="two",
                payload={"output": "done two"},
            ),
        ]
    )
    service = CoordinationTestService(
        repository=repo,
        fleet_repository=fleet_repo,
        member_repository=member_repo,
        execution_query=execution_query,
        llm_judge=llm_judge,
    )

    insufficient = await service.run_coordination_test(fleet_id, execution_id, workspace_id)
    complete = await service.run_coordination_test(fleet_id, execution_id, workspace_id)

    assert insufficient.insufficient_members is True
    assert complete.insufficient_members is False
    assert complete.overall_score > 0
    assert service._normalize_judge_score(4.0, {"max_scale": 5.0}) == 0.8
    assert "one" in service._per_agent_scores(members, execution_query.journal_items)

    clickhouse = ClickHouseStub()
    evaluation_repo = SimpleNamespace(
        list_active_robustness_runs_by_agent=AsyncMock(return_value=[SimpleNamespace()])
    )
    drift_service = DriftDetectionService(
        repository=SimpleNamespace(
            session=SessionStub(), list_drift_alerts=AsyncMock(return_value=([], 0))
        ),
        evaluation_repository=evaluation_repo,
        clickhouse_client=clickhouse,
        settings=make_settings(),
        producer=None,
    )
    assert await drift_service.should_suppress("agents.demo") is True
    assert await drift_service.detect_drift("agents.demo", uuid4(), workspace_id) is None


@pytest.mark.asyncio
async def test_testing_dependency_builders_and_getters(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SessionStub()
    request = make_request(
        clients={
            "kafka": None,
            "minio": ObjectStorageStub(),
            "clickhouse": ClickHouseStub(),
            "redis": SimpleNamespace(),
            "runtime_controller": None,
            "reasoning_engine": None,
        }
    )
    app = FastAPI()
    app.state.settings = make_settings()
    app.state.clients = request.app.state.clients
    request.app = app
    execution_service = SimpleNamespace(name="execution")
    registry_service = RegistryServiceStub(profile={"purpose": "agent"})
    monkeypatch.setattr(
        "platform.testing.dependencies.build_execution_service",
        lambda **_kwargs: execution_service,
    )

    adversarial = build_adversarial_generation_service(
        session=session,
        settings=make_settings(),
        registry_service=registry_service,
    )
    suite_service = build_test_suite_generation_service(
        session=session,
        settings=make_settings(),
        producer=None,
        object_storage=ObjectStorageStub(),
        registry_service=registry_service,
    )
    drift_service = build_drift_service(
        session=session,
        settings=make_settings(),
        producer=None,
        clickhouse_client=ClickHouseStub(),
    )
    coordination = build_coordination_service(
        session=session,
        settings=make_settings(),
        producer=None,
        redis_client=SimpleNamespace(),
        object_storage=ObjectStorageStub(),
        runtime_controller=None,
        reasoning_engine=None,
    )

    assert isinstance(adversarial, AdversarialGenerationService)
    assert isinstance(suite_service, TestSuiteGenerationService)
    assert isinstance(drift_service, DriftDetectionService)
    assert isinstance(coordination, CoordinationTestService)
    assert isinstance(
        await get_adversarial_generation_service(request, session, registry_service),
        AdversarialGenerationService,
    )
    assert isinstance(
        await get_test_suite_generation_service(request, session, registry_service),
        TestSuiteGenerationService,
    )
    assert isinstance(await get_drift_service(request, session), DriftDetectionService)
    coordination_from_getter = await get_coordination_service(request, session)
    assert isinstance(coordination_from_getter, CoordinationTestService)
    assert hasattr(coordination_from_getter, "run_coordination_test")


@pytest.mark.asyncio
async def test_testing_router_wrappers_cover_endpoint_logic() -> None:
    workspace_id = uuid4()
    suite_response = GeneratedTestSuiteResponse.model_validate(
        build_suite(workspace_id=workspace_id)
    )
    case_response = AdversarialCaseListResponse(
        items=[build_adversarial_case(suite_id=suite_response.id)],
        total=1,
        page=1,
        page_size=10,
    )
    coordination_response = CoordinationTestResultResponse.model_validate(
        build_coordination_result(workspace_id=workspace_id)
    )
    alert_response = DriftAlertResponse.model_validate(build_drift_alert(workspace_id=workspace_id))
    request = make_request()
    request.headers["X-Workspace-ID"] = str(workspace_id)
    current_user = _admin_user(workspace_id)
    background = BackgroundTasks()
    suite_service = SimpleNamespace(
        start_generation=AsyncMock(return_value=suite_response),
        list_suites=AsyncMock(
            return_value=GeneratedTestSuiteListResponse(
                items=[suite_response], total=1, page=1, page_size=10
            )
        ),
        get_suite=AsyncMock(return_value=suite_response),
        list_cases=AsyncMock(return_value=case_response),
        import_to_eval_set=AsyncMock(
            return_value=ImportSuiteResponse(imported_case_count=1, eval_set_id=uuid4())
        ),
    )
    coordination_service = SimpleNamespace(
        run_coordination_test=AsyncMock(return_value=coordination_response),
        repository=SimpleNamespace(
            get_coordination_result=AsyncMock(return_value=coordination_response)
        ),
    )
    drift_service = SimpleNamespace(
        list_alerts=AsyncMock(
            return_value=DriftAlertListResponse(
                items=[alert_response], total=1, page=1, page_size=10
            )
        ),
        acknowledge_alert=AsyncMock(return_value=alert_response),
    )

    assert _actor_id(current_user) == UUID(str(current_user["sub"]))
    assert _workspace_id(request, current_user, workspace_id) == workspace_id
    with pytest.raises(AuthorizationError):
        _require_roles({"roles": [{"role": "viewer"}]}, {"workspace_admin"})

    generated = await generate_suite(
        GenerateSuiteRequest(
            workspace_id=workspace_id,
            agent_fqn=suite_response.agent_fqn,
            agent_id=suite_response.agent_id,
            suite_type=suite_response.suite_type,
            cases_per_category=1,
        ),
        background,
        request,
        current_user,
        suite_service,
    )
    listed = await list_suites(
        request,
        current_user,
        suite_response.agent_fqn,
        suite_response.suite_type,
        1,
        10,
        suite_service,
    )
    fetched = await get_suite(suite_response.id, request, current_user, suite_service)
    listed_cases = await list_suite_cases(
        suite_response.id, AdversarialCategory.prompt_injection, 1, 10, suite_service
    )
    imported = await import_suite(
        suite_response.id,
        ImportSuiteRequest(eval_set_id=uuid4()),
        suite_service,
    )
    coordination = await run_coordination_test(
        CoordinationTestRequest(workspace_id=workspace_id, fleet_id=uuid4(), execution_id=uuid4()),
        request,
        current_user,
        coordination_service,
    )
    fetched_coordination = await get_coordination_test(
        coordination.id, request, current_user, coordination_service
    )
    alerts = await list_drift_alerts(request, current_user, None, None, False, 1, 10, drift_service)
    acknowledged = await acknowledge_drift_alert(alert_response.id, current_user, drift_service)

    assert generated.id == suite_response.id
    assert len(background.tasks) == 1
    assert listed.total == 1
    assert fetched.id == suite_response.id
    assert listed_cases.total == 1
    assert imported.imported_case_count == 1
    assert coordination.id == coordination_response.id
    assert fetched_coordination.id == coordination_response.id
    assert alerts.total == 1
    assert acknowledged.id == alert_response.id

    empty_coordination = SimpleNamespace(
        repository=SimpleNamespace(get_coordination_result=AsyncMock(return_value=None))
    )
    with pytest.raises(ValidationError, match="Coordination test result not found"):
        await get_coordination_test(uuid4(), request, current_user, empty_coordination)


@pytest.mark.asyncio
async def test_suite_generation_and_drift_services_raise_not_found_when_entities_are_missing() -> (
    None
):
    repo = SimpleNamespace(
        session=SessionStub(),
        get_suite=AsyncMock(return_value=None),
        get_drift_alert=AsyncMock(return_value=None),
    )
    suite_service = TestSuiteGenerationService(
        repository=repo,
        evaluation_repository=SimpleNamespace(get_eval_set=AsyncMock(return_value=None)),
        settings=make_settings(),
        producer=None,
        object_storage=ObjectStorageStub(),
        adversarial_service=SimpleNamespace(generate_cases=AsyncMock()),
    )
    drift_service = DriftDetectionService(
        repository=repo,
        evaluation_repository=SimpleNamespace(
            list_active_robustness_runs_by_agent=AsyncMock(return_value=[])
        ),
        clickhouse_client=ClickHouseStub(),
        settings=make_settings(),
        producer=None,
    )

    with pytest.raises(NotFoundError):
        await suite_service.get_suite(uuid4())
    with pytest.raises(NotFoundError):
        await suite_service.generate_suite(uuid4(), cases_per_category=1)
    with pytest.raises(NotFoundError):
        await suite_service.import_to_eval_set(uuid4(), uuid4())
    with pytest.raises(NotFoundError):
        await drift_service.acknowledge_alert(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_adversarial_helpers_and_suite_background_cover_remaining_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    repo = SimpleNamespace(create_adversarial_cases=AsyncMock(side_effect=lambda cases: cases))

    class _Profile:
        def model_dump(self, *, mode: str) -> dict[str, object]:
            assert mode == "json"
            return {"purpose": "model dump profile", "tags": ["a"], "role_types": ["executor"]}

    service = AdversarialGenerationService(
        repository=repo,
        settings=make_settings(),
        registry_service=SimpleNamespace(get_agent_by_fqn=AsyncMock(return_value=_Profile())),
        model_api_url="http://model.example",
    )
    profile = await service._get_agent_profile(workspace_id, "agents.demo")
    fallback_profile = await AdversarialGenerationService(
        repository=repo,
        settings=make_settings(),
        registry_service=SimpleNamespace(
            get_agent_by_fqn=AsyncMock(side_effect=RuntimeError("boom"))
        ),
    )._get_agent_profile(workspace_id, "agents.demo")

    assert profile["purpose"] == "model dump profile"
    assert fallback_profile["purpose"] == "general assistant"

    class _Response:
        def __init__(self, payload: object) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return self._payload

    class _Client:
        def __init__(self, payload: object) -> None:
            self.payload = payload

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, *_args: object, **_kwargs: object) -> _Response:
            return _Response(self.payload)

    monkeypatch.setattr(
        "platform.testing.adversarial_service.httpx.AsyncClient",
        lambda timeout: _Client(
            {
                "cases": '[{"input_data": {"prompt": "provider"}, "expected_behavior": "refuse"}]'
            }
        ),
    )
    parsed_cases = await service._fetch_provider_cases("prompt")
    monkeypatch.setattr(
        "platform.testing.adversarial_service.httpx.AsyncClient",
        lambda timeout: _Client({"cases": "not-json"}),
    )
    invalid_cases = await service._fetch_provider_cases("prompt")
    monkeypatch.setattr(
        service,
        "_fetch_provider_cases",
        AsyncMock(return_value=[{"input_data": "bad", "expected_behavior": None}]),
    )
    fallback_cases = await service._generate_category_cases(
        category=AdversarialCategory.ambiguous,
        agent_fqn="agents.demo",
        prompt="prompt",
        cases_per_category=2,
    )

    assert parsed_cases[0]["expected_behavior"] == "refuse"
    assert invalid_cases == []
    assert len(fallback_cases) == 2
    for category in AdversarialCategory:
        fallback = AdversarialGenerationService._fallback_case("agents.demo", category, 1)
        assert fallback["input_data"]["agent_fqn"] == "agents.demo"
        assert fallback["expected_behavior"]

    request = make_request()
    current_user = {"sub": str(uuid4()), "workspace_id": str(workspace_id), "roles": []}
    assert _workspace_id(request, current_user) == workspace_id
    assert _workspace_id(request, {"sub": str(uuid4())}, workspace_id) == workspace_id
    with pytest.raises(ValidationError, match="does not match"):
        _workspace_id(make_request(), current_user, uuid4())

    class _SessionContext:
        def __init__(self, session: SessionStub) -> None:
            self.session = session

        async def __aenter__(self) -> SessionStub:
            return self.session

        async def __aexit__(self, *_args: object) -> None:
            return None

    app = FastAPI()
    app.state.settings = make_settings()
    app.state.clients = {"kafka": None, "minio": ObjectStorageStub()}

    success_session = SessionStub()
    monkeypatch.setattr(
        "platform.testing.router.database.AsyncSessionLocal",
        lambda: _SessionContext(success_session),
    )
    monkeypatch.setattr(
        "platform.testing.router.build_test_suite_generation_service",
        lambda **_kwargs: SimpleNamespace(generate_suite=AsyncMock()),
    )
    await _generate_suite_background(app, uuid4(), 3)
    assert success_session.commits == 1

    failed_session = SessionStub()
    monkeypatch.setattr(
        "platform.testing.router.database.AsyncSessionLocal",
        lambda: _SessionContext(failed_session),
    )
    monkeypatch.setattr(
        "platform.testing.router.build_test_suite_generation_service",
        lambda **_kwargs: SimpleNamespace(
            generate_suite=AsyncMock(side_effect=RuntimeError("suite generation failed"))
        ),
    )
    with pytest.raises(RuntimeError, match="suite generation failed"):
        await _generate_suite_background(app, uuid4(), 1)
    assert failed_session.rollbacks == 1


@pytest.mark.asyncio
async def test_testing_services_cover_validation_and_early_return_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    existing_suite = build_suite(workspace_id=workspace_id, case_count=2)
    repo = SimpleNamespace(
        session=SessionStub(),
        get_suite=AsyncMock(return_value=existing_suite),
        update_suite=AsyncMock(side_effect=lambda model, **fields: _apply_updates(model, **fields)),
        get_drift_alert=AsyncMock(return_value=None),
    )
    adversarial = SimpleNamespace(generate_cases=AsyncMock())
    suite_service = TestSuiteGenerationService(
        repository=repo,
        evaluation_repository=SimpleNamespace(get_eval_set=AsyncMock(return_value=None)),
        settings=make_settings(),
        producer=None,
        object_storage=ObjectStorageStub(),
        adversarial_service=adversarial,
    )
    existing = await suite_service.generate_suite(existing_suite.id, cases_per_category=3)
    assert existing.case_count == 2
    adversarial.generate_cases.assert_not_called()

    archived_eval_set = build_eval_set(workspace_id=workspace_id, status=EvalSetStatus.archived)
    archived_suite_service = TestSuiteGenerationService(
        repository=SimpleNamespace(
            session=SessionStub(),
            get_suite=AsyncMock(return_value=build_suite(workspace_id=workspace_id)),
            list_adversarial_cases=AsyncMock(return_value=([build_adversarial_case()], 1)),
            update_suite=AsyncMock(),
        ),
        evaluation_repository=SimpleNamespace(
            get_eval_set=AsyncMock(return_value=archived_eval_set),
            get_next_case_position=AsyncMock(return_value=1),
            create_benchmark_case=AsyncMock(),
        ),
        settings=make_settings(),
        producer=None,
        object_storage=ObjectStorageStub(),
        adversarial_service=adversarial,
    )
    with pytest.raises(ValidationError, match="archived"):
        await archived_suite_service.import_to_eval_set(uuid4(), uuid4())

    drift_service = DriftDetectionService(
        repository=repo,
        evaluation_repository=SimpleNamespace(
            list_active_robustness_runs_by_agent=AsyncMock(return_value=[])
        ),
        clickhouse_client=ClickHouseStub(),
        settings=make_settings(),
        producer=None,
    )
    assert await drift_service.detect_drift("agents.demo", uuid4(), workspace_id) is None
    assert hasattr(CoordinationTestServiceInterface, "run_coordination_test")
    assert _clean_optional_text("  value  ") == "value"
    assert _clean_optional_text("   ") is None

    generating_suite = build_suite(workspace_id=workspace_id, case_count=0)
    big_cases = [build_adversarial_case(suite_id=generating_suite.id) for _ in range(501)]
    archive_storage = ObjectStorageStub()
    archiving_service = TestSuiteGenerationService(
        repository=SimpleNamespace(
            session=SessionStub(),
            get_suite=AsyncMock(return_value=generating_suite),
            update_suite=AsyncMock(
                side_effect=lambda model, **fields: _apply_updates(model, **fields)
            ),
        ),
        evaluation_repository=SimpleNamespace(get_eval_set=AsyncMock(return_value=None)),
        settings=make_settings(),
        producer=None,
        object_storage=archive_storage,
        adversarial_service=SimpleNamespace(generate_cases=AsyncMock(return_value=big_cases)),
    )
    archived_response = await archiving_service.generate_suite(
        generating_suite.id,
        cases_per_category=1,
    )
    assert archived_response.artifact_key == f"{generating_suite.id}/suite.json"

    missing_eval_set_service = TestSuiteGenerationService(
        repository=SimpleNamespace(
            session=SessionStub(),
            get_suite=AsyncMock(return_value=build_suite(workspace_id=workspace_id)),
            list_adversarial_cases=AsyncMock(return_value=([build_adversarial_case()], 1)),
            update_suite=AsyncMock(),
        ),
        evaluation_repository=SimpleNamespace(
            get_eval_set=AsyncMock(return_value=None),
            get_next_case_position=AsyncMock(return_value=1),
            create_benchmark_case=AsyncMock(),
        ),
        settings=make_settings(),
        producer=None,
        object_storage=ObjectStorageStub(),
        adversarial_service=adversarial,
    )
    with pytest.raises(NotFoundError, match="Evaluation set not found"):
        await missing_eval_set_service.import_to_eval_set(uuid4(), uuid4())

    zero_schema_service = DriftDetectionService(
        repository=repo,
        evaluation_repository=SimpleNamespace(
            list_active_robustness_runs_by_agent=AsyncMock(return_value=[])
        ),
        clickhouse_client=ClickHouseStub(),
        settings=make_settings(),
        producer=None,
    )
    with monkeypatch.context() as local_monkeypatch:
        local_monkeypatch.setattr(
            "platform.testing.drift_service._SCHEMA_PATH",
            SimpleNamespace(read_text=lambda encoding: "   "),
        )
        await zero_schema_service.ensure_schema()

    zero_stddev_clickhouse = ClickHouseStub()
    zero_stddev_clickhouse.query_results.extend(
        [[{"baseline_value": 0.9, "stddev_value": 0.0}], [{"score": 0.2}]]
    )
    zero_stddev_service = DriftDetectionService(
        repository=repo,
        evaluation_repository=SimpleNamespace(
            list_active_robustness_runs_by_agent=AsyncMock(return_value=[])
        ),
        clickhouse_client=zero_stddev_clickhouse,
        settings=make_settings(),
        producer=None,
    )
    assert await zero_stddev_service.detect_drift("agents.demo", uuid4(), workspace_id) is None

    no_latest_clickhouse = ClickHouseStub()
    no_latest_clickhouse.query_results.extend(
        [[{"baseline_value": 0.9, "stddev_value": 0.1}], []]
    )
    no_latest_service = DriftDetectionService(
        repository=repo,
        evaluation_repository=SimpleNamespace(
            list_active_robustness_runs_by_agent=AsyncMock(return_value=[])
        ),
        clickhouse_client=no_latest_clickhouse,
        settings=make_settings(),
        producer=None,
    )
    assert await no_latest_service.detect_drift("agents.demo", uuid4(), workspace_id) is None

    low_drift_clickhouse = ClickHouseStub()
    low_drift_clickhouse.query_results.extend(
        [[{"baseline_value": 0.9, "stddev_value": 0.1}], [{"score": 0.85}]]
    )
    low_drift_service = DriftDetectionService(
        repository=repo,
        evaluation_repository=SimpleNamespace(
            list_active_robustness_runs_by_agent=AsyncMock(return_value=[])
        ),
        clickhouse_client=low_drift_clickhouse,
        settings=make_settings(),
        producer=None,
    )
    assert await low_drift_service.detect_drift("agents.demo", uuid4(), workspace_id) is None
