from __future__ import annotations

import asyncio
import importlib
import importlib.util
import os
import sys
import threading
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

local_platform_dir = SRC_DIR / "platform"
loaded_platform = sys.modules.get("platform")
loaded_from = getattr(loaded_platform, "__file__", None) if loaded_platform is not None else None
is_local_platform = loaded_from is not None and Path(loaded_from).resolve().is_relative_to(
    local_platform_dir
)
if not is_local_platform:
    sys.modules.pop("platform", None)
    spec = importlib.util.spec_from_file_location(
        "platform",
        local_platform_dir / "__init__.py",
        submodule_search_locations=[str(local_platform_dir)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load local platform package from {local_platform_dir}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["platform"] = module
    spec.loader.exec_module(module)

Base = importlib.import_module("platform.common.models").Base
importlib.import_module("platform.auth.models")
importlib.import_module("platform.accounts.models")
importlib.import_module("platform.workspaces.models")
importlib.import_module("platform.two_person_approval.models")
importlib.import_module("platform.analytics.models")
importlib.import_module("platform.registry.models")
importlib.import_module("platform.context_engineering.models")
importlib.import_module("platform.memory.models")
importlib.import_module("platform.interactions.models")
importlib.import_module("platform.connectors.models")
importlib.import_module("platform.policies.models")
importlib.import_module("platform.workflows.models")
importlib.import_module("platform.execution.models")
importlib.import_module("platform.trust.models")
importlib.import_module("platform.fleets.models")
importlib.import_module("platform.fleet_learning.models")
importlib.import_module("platform.evaluation.models")
importlib.import_module("platform.testing.models")
importlib.import_module("platform.agentops.models")
importlib.import_module("platform.composition.models")
importlib.import_module("platform.discovery.models")
importlib.import_module("platform.simulation.models")
importlib.import_module("platform.a2a_gateway.models")
importlib.import_module("platform.mcp.models")
importlib.import_module("platform.audit.models")
importlib.import_module("platform.security_compliance.models")
importlib.import_module("platform.incident_response.models")
importlib.import_module("platform.localization.models")
importlib.import_module("platform.status_page.models")
importlib.import_module("platform.tenants.models")

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    raise RuntimeError("Offline migrations are not supported for this project.")


async def run_migrations_online() -> None:
    database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_DSN")
    if not database_url:
        raise RuntimeError("DATABASE_URL or POSTGRES_DSN must be set for Alembic migrations.")
    connectable = create_async_engine(database_url, poolclass=pool.NullPool)

    async with connectable.begin() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def _run_migrations_in_thread() -> None:
    """Run async migrations in a fresh thread with its own event loop.

    Required when called from within a running event loop (e.g. pytest-asyncio),
    because asyncio.run() cannot be nested inside an active loop.
    """
    asyncio.run(run_migrations_online())


if context.is_offline_mode():
    run_migrations_offline()
else:
    try:
        asyncio.get_running_loop()
        # Already inside a running loop — delegate to a background thread.
        _thread = threading.Thread(target=_run_migrations_in_thread)
        _thread.start()
        _thread.join()
    except RuntimeError:
        # No running loop — safe to call asyncio.run() directly.
        asyncio.run(run_migrations_online())
