from __future__ import annotations

from datetime import UTC, datetime
from platform.audit.router import get_audit_chain_service, require_audit_reader, router
from platform.audit.schemas import SignedAttestation, VerifyResult
from platform.common.exceptions import AuthorizationError
from typing import Any

import httpx
import pytest
from fastapi import FastAPI


class FakeAuditChainService:
    async def verify(
        self,
        start_seq: int | None = None,
        end_seq: int | None = None,
    ) -> VerifyResult:
        assert start_seq == 1
        assert end_seq == 3
        return VerifyResult(valid=True, entries_checked=3)

    async def export_attestation(self, start_seq: int, end_seq: int) -> SignedAttestation:
        assert start_seq == 1
        assert end_seq == 3
        now = datetime.now(UTC)
        return SignedAttestation(
            platform="musematic",
            env="test",
            start_seq=start_seq,
            end_seq=end_seq,
            start_entry_hash="a" * 64,
            end_entry_hash="b" * 64,
            window_start_time=now,
            window_end_time=now,
            chain_entries_count=3,
            key_version=1,
            signature="c" * 128,
        )

    async def get_public_verifying_key(self) -> str:
        return "d" * 64


async def _audit_reader_override() -> dict[str, Any]:
    return {"roles": [{"role": "auditor"}]}


async def _service_override() -> FakeAuditChainService:
    return FakeAuditChainService()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_audit_chain_service] = _service_override
    app.dependency_overrides[require_audit_reader] = _audit_reader_override
    return app


@pytest.mark.asyncio
async def test_audit_chain_router_verify_and_attestation() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()),
        base_url="http://testserver",
    ) as client:
        verify = await client.get("/api/v1/security/audit-chain/verify?start_seq=1&end_seq=3")
        attestation = await client.post(
            "/api/v1/security/audit-chain/attestations",
            json={"start_seq": 1, "end_seq": 3},
        )

    assert verify.status_code == 200
    assert verify.json() == {"valid": True, "entries_checked": 3, "broken_at": None}
    assert attestation.status_code == 200
    assert attestation.json()["signature"] == "c" * 128


@pytest.mark.asyncio
async def test_audit_chain_public_key_endpoint_is_not_role_gated() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_audit_chain_service] = _service_override

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/security/audit-chain/public-key")

    assert response.status_code == 200
    assert response.json() == {"public_key": "d" * 64}


@pytest.mark.asyncio
async def test_require_audit_reader_rejects_non_auditor() -> None:
    with pytest.raises(AuthorizationError):
        await require_audit_reader({"roles": [{"role": "workspace_admin"}]})
