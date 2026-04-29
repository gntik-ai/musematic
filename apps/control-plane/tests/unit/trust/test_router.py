from __future__ import annotations

from platform.common.exceptions import AuthorizationError, ValidationError
from platform.trust.contract_schemas import (
    AgentContractUpdate,
    ContractAttachmentRequest,
    DismissSuspensionRequest,
    IssueWithCertifierRequest,
    ReassessmentCreate,
)
from platform.trust.models import TrustRecertificationRequest
from platform.trust.router import (
    _require_roles,
    _require_service_account,
    activate_certification,
    add_certification_evidence,
    archive_contract,
    attach_contract_to_interaction,
    create_certification,
    create_certifier,
    create_contract,
    create_reassessment,
    deactivate_certifier,
    dismiss_suspension,
    get_blocked_action,
    get_certification,
    get_certifier,
    get_contract,
    get_guardrail_config,
    get_recertification_request_v2,
    issue_with_certifier,
    list_agent_certifications,
    list_ate_configs,
    list_certifiers,
    list_circuit_breaker_configs,
    list_contract_breaches,
    list_contracts,
    list_prescreener_rule_sets,
    list_reassessments,
    list_recertification_requests_v2,
    update_contract,
)
from platform.trust.schemas import CertificationCreate, EvidenceRefCreate
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from starlette.datastructures import QueryParams

from tests.trust_support import (
    admin_user,
    build_certification,
    build_certifier_create,
    build_contract_create,
    build_trust_app,
    build_trust_bundle,
    trust_certifier_user,
    workspace_member_user,
)


@pytest.mark.asyncio
async def test_trust_router_requires_auth_with_real_middleware() -> None:
    app, _bundle = build_trust_app(require_auth_middleware=True)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/trust/agents/agent-1/tier")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_trust_router_direct_handlers_cover_missing_branches() -> None:
    bundle = build_trust_bundle()
    certification = build_certification()
    bundle.repository.certifications.append(certification)

    with pytest.raises(AuthorizationError):
        _require_roles({"roles": []}, {"platform_admin"})
    with pytest.raises(AuthorizationError):
        _require_service_account({"roles": [], "type": "human"})
    _require_service_account({"roles": [{"role": "platform_service"}], "type": "human"})

    fetched = await get_certification(
        certification.id,
        certification_service=bundle.certification_service,
    )
    assert fetched.id == certification.id

    with pytest.raises(ValidationError):
        await get_blocked_action(
            uuid4(),
            current_user=trust_certifier_user(),
            guardrail_service=bundle.guardrail_service,
        )
    with pytest.raises(ValidationError):
        await get_guardrail_config(
            workspace_id="workspace-404",
            fleet_id=None,
            guardrail_service=bundle.guardrail_service,
        )

    rule_sets = await list_prescreener_rule_sets(
        current_user=admin_user(),
        prescreener_service=bundle.prescreener_service,
    )
    ate_configs = await list_ate_configs(
        workspace_id="workspace-1",
        current_user=workspace_member_user(),
        ate_service=bundle.ate_service,
    )
    cb_configs = await list_circuit_breaker_configs(
        workspace_id="workspace-1",
        current_user=admin_user(),
        circuit_breaker_service=bundle.circuit_breaker_service,
    )

    assert rule_sets.total == 0
    assert ate_configs.total == 0
    assert cb_configs.total == 0


@pytest.mark.asyncio
async def test_trust_router_direct_contract_and_certification_crud_handlers() -> None:
    bundle = build_trust_bundle()
    admin = admin_user()
    certifier_user = trust_certifier_user()

    created_contract = await create_contract(
        build_contract_create(),
        current_user=admin,
        contract_service=bundle.contract_service,
    )
    listed_contracts = await list_contracts(
        agent_id=None,
        include_archived=False,
        current_user=workspace_member_user(),
        contract_service=bundle.contract_service,
    )
    fetched_contract = await get_contract(
        created_contract.id,
        current_user=admin,
        contract_service=bundle.contract_service,
    )
    updated_contract = await update_contract(
        created_contract.id,
        AgentContractUpdate(task_scope="Updated by router"),
        current_user=admin,
        contract_service=bundle.contract_service,
    )
    attach_response = await attach_contract_to_interaction(
        created_contract.id,
        ContractAttachmentRequest(interaction_id=uuid4()),
        current_user=admin,
        contract_service=bundle.contract_service,
    )
    stored_contract = await bundle.repository.get_contract(created_contract.id)
    assert stored_contract is not None
    await bundle.contract_service.record_breach(
        contract=stored_contract,
        target_type="interaction",
        target_id=uuid4(),
        breached_term="quality_threshold",
        observed_value={"accuracy_min": 0.4},
        threshold_value={"accuracy_min": 0.9},
        enforcement_action="warn",
        enforcement_outcome="success",
    )
    breaches = await list_contract_breaches(
        created_contract.id,
        target_type=None,
        start=None,
        end=None,
        page=1,
        page_size=50,
        current_user=admin,
        contract_service=bundle.contract_service,
    )

    certifier = await create_certifier(
        build_certifier_create(),
        current_user=admin,
        certification_service=bundle.certification_service,
    )
    listed_certifiers = await list_certifiers(
        include_inactive=False,
        current_user=admin,
        certification_service=bundle.certification_service,
    )
    fetched_certifier = await get_certifier(
        certifier.id,
        current_user=admin,
        certification_service=bundle.certification_service,
    )
    certification = await create_certification(
        CertificationCreate(
            agent_id="agent-router",
            agent_fqn="fleet:agent-router",
            agent_revision_id="rev-router",
        ),
        current_user=certifier_user,
        certification_service=bundle.certification_service,
    )
    activated = await activate_certification(
        certification.id,
        current_user=certifier_user,
        certification_service=bundle.certification_service,
    )
    evidence = await add_certification_evidence(
        certification.id,
        EvidenceRefCreate(
            evidence_type="test_results",
            source_ref_type="suite",
            source_ref_id="run-1",
            summary="ok",
        ),
        current_user=certifier_user,
        certification_service=bundle.certification_service,
    )
    issued = await issue_with_certifier(
        certification.id,
        IssueWithCertifierRequest(
            certifier_id=certifier.id,
            scope="financial_calculations",
        ),
        current_user=admin,
        certification_service=bundle.certification_service,
    )
    reassessment = await create_reassessment(
        certification.id,
        ReassessmentCreate(verdict="fail", notes="needs review"),
        current_user=admin,
        certification_service=bundle.certification_service,
    )
    await bundle.repository.create_recertification_request(
        TrustRecertificationRequest(
            certification_id=certification.id,
            trigger_type="signal",
            trigger_reference="router-dismiss",
            deadline=None,
            resolution_status="pending",
        )
    )
    reassessments = await list_reassessments(
        certification.id,
        current_user=admin,
        certification_service=bundle.certification_service,
    )
    dismissed = await dismiss_suspension(
        certification.id,
        DismissSuspensionRequest(justification="Manual review completed successfully"),
        current_user=admin,
        certification_service=bundle.certification_service,
    )
    requests = await list_recertification_requests_v2(
        certification_id=None,
        current_user=admin,
        certification_service=bundle.certification_service,
        status="dismissed",
    )
    request = await get_recertification_request_v2(
        requests.items[0].id,
        current_user=admin,
        certification_service=bundle.certification_service,
    )
    certs = await list_agent_certifications(
        "agent-router",
        SimpleNamespace(query_params=QueryParams("")),
        certification_service=bundle.certification_service,
    )
    deactivate_response = await deactivate_certifier(
        certifier.id,
        current_user=admin,
        certification_service=bundle.certification_service,
    )
    archive_response = await archive_contract(
        created_contract.id,
        current_user=admin,
        contract_service=bundle.contract_service,
    )

    assert listed_contracts.total == 1
    assert fetched_contract.id == created_contract.id
    assert updated_contract.task_scope == "Updated by router"
    assert attach_response.status_code == 204
    assert breaches.total == 1
    assert listed_certifiers.total == 1
    assert fetched_certifier.id == certifier.id
    assert activated.status.value == "active"
    assert evidence.source_ref_id == "run-1"
    assert issued.external_certifier_id == certifier.id
    assert reassessment.verdict == "fail"
    assert reassessments.total == 1
    assert dismissed.status.value == "active"
    assert requests.total == 1
    assert request.id == requests.items[0].id
    assert certs.total == 1
    assert deactivate_response.status_code == 204
    assert archive_response.status_code == 204
