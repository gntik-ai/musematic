from platform.api.health import router as health_router

from fastapi import APIRouter

router = APIRouter()
router.include_router(health_router)
