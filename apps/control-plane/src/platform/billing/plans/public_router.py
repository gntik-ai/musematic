from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/public/plans", tags=["billing", "public-plans"])
