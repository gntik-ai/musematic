from __future__ import annotations

import io
import os
from contextlib import redirect_stdout
from pathlib import Path

from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = ROOT / "migrations" / "alembic.ini"


def make_async_database_url(sync_url: str) -> str:
    # testcontainers may return postgresql+psycopg2:// or plain postgresql://
    url = sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def make_alembic_config(database_url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    os.environ["DATABASE_URL"] = database_url
    return config


def run_alembic(database_url: str, action: str, revision: str) -> str:
    config = make_alembic_config(database_url)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        getattr(command, action)(config, revision)
    return buffer.getvalue()


def run_alembic_branches(database_url: str) -> str:
    config = make_alembic_config(database_url)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        command.branches(config, verbose=True)
    return buffer.getvalue()
