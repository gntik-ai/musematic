from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from platform.billing.plans.admin_router import router as admin_plans_router
from platform.common.config import settings as default_settings
from platform.common.dependencies import get_current_user, get_db
from platform.common.exceptions import PlatformError, platform_exception_handler
from typing import Any
from uuid import uuid4

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class BillingKafkaMock:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def publish(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append({"args": args, "kwargs": kwargs})


@dataclass
class BillingAdminClient:
    client: AsyncClient
    producer: BillingKafkaMock


@pytest_asyncio.fixture
async def billing_admin_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[BillingAdminClient]:
    producer = BillingKafkaMock()
    app = FastAPI()
    app.state.settings = default_settings
    app.state.clients = {"kafka": producer}
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(admin_plans_router)

    async def override_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def superadmin_user() -> dict[str, Any]:
        return {"sub": str(uuid4()), "roles": ["superadmin"]}

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = superadmin_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield BillingAdminClient(client=client, producer=producer)
