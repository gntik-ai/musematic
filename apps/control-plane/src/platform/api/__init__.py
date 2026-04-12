from platform.analytics.router import router as analytics_router
from platform.api.health import router as health_router
from platform.connectors.router import router as connectors_router
from platform.context_engineering.router import router as context_engineering_router
from platform.execution.router import router as execution_router
from platform.interactions.router import router as interactions_router
from platform.marketplace.router import router as marketplace_router
from platform.memory.router import router as memory_router
from platform.policies.router import router as policies_router
from platform.registry.router import router as registry_router
from platform.workflows.router import router as workflows_router

from fastapi import APIRouter

router = APIRouter()
router.include_router(health_router)
router.include_router(analytics_router)
router.include_router(registry_router)
router.include_router(context_engineering_router)
router.include_router(memory_router)
router.include_router(marketplace_router)
router.include_router(interactions_router)
router.include_router(connectors_router)
router.include_router(policies_router)
router.include_router(workflows_router)
router.include_router(execution_router)
