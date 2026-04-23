from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.trust.models import CertificationStatus, TrustRecertificationRequest
from uuid import UUID, uuid4

import httpx
import pytest

from tests.trust_support import (
    admin_user,
    build_certification_create,
    build_certifier_create,
    build_contract_create,
    build_trust_app,
    build_trust_bundle,
    workspace_member_user,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_contract_endpoints_and_compliance_rates() -> None:
    bundle = build_trust_bundle()
    app, _bundle = build_trust_app(bundle=bundle, current_user=admin_user())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        create_response = await client.post(
            "/api/v1/trust/contracts",
            json=build_contract_create().model_dump(mode="json"),
        )
        assert create_response.status_code == 201
        contract_id = create_response.json()["id"]

        execution_id = str(uuid4())
        attach_response = await client.post(
            f"/api/v1/trust/contracts/{contract_id}/attach-execution",
            json={"execution_id": execution_id},
        )
        assert attach_response.status_code == 204

        contract = await bundle.repository.get_contract(UUID(contract_id))
        assert contract is not None
        breach = await bundle.contract_service.record_breach(
            contract=contract,
            target_type="execution",
            target_id=UUID(execution_id),
            breached_term="time_constraint",
            observed_value={"elapsed_seconds": 15.0},
            threshold_value={"time_constraint_seconds": 10},
            enforcement_action="terminate",
            enforcement_outcome="success",
        )
        assert breach.contract_id == contract.id

        list_response = await client.get(f"/api/v1/trust/contracts/{contract_id}/breaches")
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1

        bundle.repository.seed_interaction_attachment(
            interaction_id=uuid4(),
            contract_id=contract.id,
            snapshot=bundle.contract_service._snapshot(contract),
            created_at=datetime.now(UTC) - timedelta(hours=1),
            workspace_id=contract.workspace_id,
        )
        rates = await client.get(
            "/api/v1/trust/compliance/rates",
            params={
                "scope": "workspace",
                "scope_id": str(contract.workspace_id),
                "start": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
                "end": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                "bucket": "daily",
            },
        )
        assert rates.status_code == 200
        body = rates.json()
        assert body["total_contract_attached"] == 2
        assert body["terminated"] == 1
        assert body["compliance_rate"] == pytest.approx(0.5)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_certifier_and_certification_contract_flows() -> None:
    bundle = build_trust_bundle()
    app, _bundle = build_trust_app(bundle=bundle, current_user=admin_user())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        certifier_response = await client.post(
            "/api/v1/trust/certifiers",
            json=build_certifier_create().model_dump(mode="json"),
        )
        assert certifier_response.status_code == 201
        certifier_id = certifier_response.json()["id"]

        certification_response = await client.post(
            "/api/v1/trust/certifications",
            json=build_certification_create().model_dump(mode="json"),
        )
        assert certification_response.status_code == 201
        certification_id = certification_response.json()["id"]

        issued = await client.post(
            f"/api/v1/trust/certifications/{certification_id}/issue-with-certifier",
            json={"certifier_id": certifier_id, "scope": "financial_calculations"},
        )
        assert issued.status_code == 200
        assert issued.json()["external_certifier_id"] == certifier_id

        invalid_scope = await client.post(
            f"/api/v1/trust/certifications/{certification_id}/issue-with-certifier",
            json={"certifier_id": certifier_id, "scope": "medical_diagnosis"},
        )
        assert invalid_scope.status_code == 422

        activated = await client.post(
            f"/api/v1/trust/certifications/{certification_id}/activate",
        )
        assert activated.status_code == 200

        stored_cert = await bundle.repository.get_certification(UUID(certification_id))
        assert stored_cert is not None
        stored_cert.expires_at = datetime.now(UTC) + timedelta(days=2)
        await bundle.surveillance_service.run_surveillance_cycle()
        assert stored_cert.status.value == "expiring"

        stored_cert.expires_at = datetime.now(UTC) - timedelta(minutes=5)
        expired_count = await bundle.certification_service.expire_stale()
        assert expired_count == 1
        assert stored_cert.status.value == "expired"

        stored_cert.status = CertificationStatus.suspended
        request = await bundle.repository.create_recertification_request(
            TrustRecertificationRequest(
                certification_id=stored_cert.id,
                trigger_type="signal",
                trigger_reference="evt-2",
                deadline=datetime.now(UTC) + timedelta(days=1),
                resolution_status="pending",
            )
        )
        dismissed = await client.post(
            f"/api/v1/trust/certifications/{certification_id}/dismiss-suspension",
            json={"justification": "Reviewed manually and accepted."},
        )
        assert dismissed.status_code == 200
        assert dismissed.json()["status"] == "active"

        reassessment = await client.post(
            f"/api/v1/trust/certifications/{certification_id}/reassessments",
            json={"verdict": "fail", "notes": "manual review found drift"},
        )
        assert reassessment.status_code == 201
        listed = await client.get(
            f"/api/v1/trust/certifications/{certification_id}/reassessments"
        )
        assert listed.status_code == 200
        assert listed.json()["total"] == 1

        requests = await client.get("/api/v1/trust/recertification-requests")
        assert requests.status_code == 200
        assert requests.json()["total"] == 1
        assert requests.json()["items"][0]["id"] == str(request.id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_compliance_endpoint_rejects_non_compliance_user() -> None:
    bundle = build_trust_bundle()
    app, _bundle = build_trust_app(
        bundle=bundle,
        current_user=workspace_member_user(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        denied = await client.get(
            "/api/v1/trust/compliance/rates",
            params={
                "scope": "workspace",
                "scope_id": workspace_member_user()["workspace_id"],
                "start": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
                "end": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                "bucket": "daily",
            },
        )
    assert denied.status_code == 403
