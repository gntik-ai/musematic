from __future__ import annotations

from platform.testing.router import router as testing_router

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/testing")
router.include_router(testing_router)
