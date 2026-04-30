from __future__ import annotations

from pathlib import Path

from .conftest import control_plane_python


def test_mock_mode_reads_json_dict(mock_mode_temp_file: Path) -> None:
    mock_mode_temp_file.write_text(
        '{"secret/data/musematic/dev/oauth/google": {"client_secret": "mock-secret"}}',
        encoding="utf-8",
    )
    result = control_plane_python(
        """
import asyncio, os
from platform.common.config import PlatformSettings
from platform.common.secret_provider import MockSecretProvider

async def main():
    provider = MockSecretProvider(PlatformSettings(), secrets_file=os.environ["MOCK_FILE"])
    print(await provider.get("secret/data/musematic/dev/oauth/google", "client_secret"))

asyncio.run(main())
""",
        env={"MOCK_FILE": str(mock_mode_temp_file)},
    )
    assert result.stdout.strip() == "mock-secret"


def test_mock_mode_env_fallback(mock_mode_temp_file: Path) -> None:
    path = "secret/data/musematic/dev/oauth/missing"
    env_key = "CONNECTOR_SECRET_VALUE_SECRET_DATA_MUSEMATIC_DEV_OAUTH_MISSING"
    result = control_plane_python(
        """
import asyncio, os
from platform.common.config import PlatformSettings
from platform.common.secret_provider import MockSecretProvider

async def main():
    provider = MockSecretProvider(PlatformSettings(), secrets_file=os.environ["MOCK_FILE"])
    print(await provider.get(os.environ["MOCK_PATH"]))

asyncio.run(main())
""",
        env={"MOCK_FILE": str(mock_mode_temp_file), "MOCK_PATH": path, env_key: "env-secret"},
    )
    assert result.stdout.strip() == "env-secret"


def test_mock_mode_missing_secret_fails(mock_mode_temp_file: Path) -> None:
    result = control_plane_python(
        """
import asyncio, os
from platform.common.config import PlatformSettings
from platform.common.secret_provider import CredentialUnavailableError, MockSecretProvider

async def main():
    provider = MockSecretProvider(PlatformSettings(), secrets_file=os.environ["MOCK_FILE"])
    try:
        await provider.get("secret/data/musematic/dev/oauth/missing")
    except CredentialUnavailableError:
        print("missing")

asyncio.run(main())
""",
        env={"MOCK_FILE": str(mock_mode_temp_file)},
    )
    assert result.stdout.strip() == "missing"


def test_mock_mode_rejects_noncanonical_path(mock_mode_temp_file: Path) -> None:
    result = control_plane_python(
        """
import asyncio, os
from platform.common.config import PlatformSettings
from platform.common.secret_provider import InvalidVaultPathError, MockSecretProvider

async def main():
    provider = MockSecretProvider(PlatformSettings(), secrets_file=os.environ["MOCK_FILE"])
    try:
        await provider.get("vault/google")
    except InvalidVaultPathError:
        print("invalid")

asyncio.run(main())
""",
        env={"MOCK_FILE": str(mock_mode_temp_file)},
    )
    assert result.stdout.strip() == "invalid"


def test_mock_mode_put_list_health(mock_mode_temp_file: Path) -> None:
    result = control_plane_python(
        """
import asyncio, os
from platform.common.config import PlatformSettings
from platform.common.secret_provider import MockSecretProvider

async def main():
    provider = MockSecretProvider(PlatformSettings(), secrets_file=os.environ["MOCK_FILE"])
    path = "secret/data/musematic/dev/accounts/bootstrap"
    await provider.put(path, {"value": "written"})
    health = await provider.health_check()
    print(f"{await provider.get(path)}:{(await provider.list_versions(path))[0]}:{health.status}")

asyncio.run(main())
""",
        env={"MOCK_FILE": str(mock_mode_temp_file)},
    )
    assert result.stdout.strip() == "written:1:green"
