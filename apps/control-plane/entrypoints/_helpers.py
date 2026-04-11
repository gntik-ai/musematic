from __future__ import annotations

import asyncio

from platform.main import create_app


def run_uvicorn_profile(profile: str, port: int) -> None:
    import uvicorn

    uvicorn.run(
        lambda: create_app(profile=profile),
        factory=True,
        host="0.0.0.0",
        port=port,
        lifespan="on",
    )


async def _run_worker_profile(profile: str) -> None:
    app = create_app(profile=profile)
    async with app.router.lifespan_context(app):
        consumer = app.state.clients.get("kafka_consumer")
        if consumer is not None:
            await consumer.start()
        await asyncio.Event().wait()


def run_worker_profile(profile: str) -> None:
    asyncio.run(_run_worker_profile(profile))
