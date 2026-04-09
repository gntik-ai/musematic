from __future__ import annotations

import asyncio
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
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from platform.common.models import Base

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
    database_url = os.environ["DATABASE_URL"]
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
