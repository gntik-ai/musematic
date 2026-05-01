from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(
    prefix="/api/v1/admin/subscriptions",
    tags=["admin", "billing", "subscriptions"],
)
