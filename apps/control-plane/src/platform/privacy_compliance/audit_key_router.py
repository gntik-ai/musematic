from __future__ import annotations

from platform.privacy_compliance.dependencies import require_privacy_reader
from platform.privacy_compliance.services.tombstone_signer import TombstoneSigner
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/api/v1/security", tags=["admin", "audit-chain"])


@router.get(
    "/audit-chain/public-key",
    response_class=PlainTextResponse,
    tags=["admin", "audit-chain"],
)
async def get_public_key(
    request: Request,
    _: dict[str, Any] = Depends(require_privacy_reader),
) -> str:
    signer = cast(TombstoneSigner, request.app.state.clients["audit_signer"])
    return await signer.public_key_pem()
