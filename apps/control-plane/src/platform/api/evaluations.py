from __future__ import annotations

from platform.evaluation.router import router as evaluation_router

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/evaluations")
router.include_router(evaluation_router)
