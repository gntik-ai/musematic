from __future__ import annotations

import asyncio
from platform.common.logging import configure_logging
from platform.main import create_app

PROFILE_SERVICE_NAMES = {
    "api": "api",
    "scheduler": "scheduler",
    "worker": "worker",
    "context-engineering": "context-engineering",
    "projection-indexer": "projection-indexer",
    "trust-certifier": "trust-certifier",
    "agentops-testing": "agentops-testing",
}


def run_uvicorn_profile(profile: str, port: int) -> None:
    import uvicorn

    configure_logging(PROFILE_SERVICE_NAMES.get(profile, profile), "platform-control")
    uvicorn.run(
        lambda: create_app(profile=profile),
        factory=True,
        host="0.0.0.0",
        port=port,
        lifespan="on",
    )


async def _run_worker_profile(profile: str) -> None:
    configure_logging(PROFILE_SERVICE_NAMES.get(profile, profile), "platform-control")
    app = create_app(profile=profile)
    async with app.router.lifespan_context(app):
        await asyncio.Event().wait()


def run_worker_profile(profile: str) -> None:
    asyncio.run(_run_worker_profile(profile))
