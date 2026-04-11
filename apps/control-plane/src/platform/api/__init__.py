from platform.analytics.router import router as analytics_router
from platform.api.health import router as health_router
from platform.registry.router import router as registry_router

from fastapi import APIRouter

router = APIRouter()
router.include_router(health_router)
router.include_router(analytics_router)
router.include_router(registry_router)
