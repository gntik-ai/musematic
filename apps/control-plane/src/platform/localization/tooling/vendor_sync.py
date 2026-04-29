from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import tempfile
import urllib.request
import zipfile
from collections.abc import Sequence
from pathlib import Path
from platform.common.config import PlatformSettings
from platform.common.secret_provider import MockSecretProvider
from platform.connectors.exceptions import CredentialUnavailableError
from platform.localization.constants import DEFAULT_LOCALE, LOCALES
from typing import Any

DEFAULT_TOKEN_REF = "secret/data/musematic/ci/connectors/localization/vendor-api-token"
LOKALISE_DOWNLOAD_URL = "https://api.lokalise.com/api2/projects/{project_id}/files/download"


async def sync_lokalise_catalogues(
    *,
    project_id: str,
    token_ref: str,
    messages_dir: Path,
    secrets_file: str,
) -> int:
    provider = MockSecretProvider(PlatformSettings(), secrets_file=secrets_file)
    try:
        token = await provider.get(token_ref)
    except CredentialUnavailableError:
        print("Localization vendor sync skipped: vendor API token is not configured.")
        return 0

    if not project_id:
        print("Localization vendor sync skipped: LOKALISE_PROJECT_ID is not configured.")
        return 0

    bundle_url = await asyncio.to_thread(_request_lokalise_bundle_url, project_id, token)
    with tempfile.TemporaryDirectory(prefix="musematic-localization-") as raw_tmpdir:
        tmpdir = Path(raw_tmpdir)
        bundle_path = tmpdir / "translations.zip"
        await asyncio.to_thread(_download_file, bundle_url, bundle_path)
        extract_dir = tmpdir / "bundle"
        extract_dir.mkdir()
        with zipfile.ZipFile(bundle_path) as archive:
            archive.extractall(extract_dir)

        await asyncio.to_thread(messages_dir.mkdir, parents=True, exist_ok=True)
        copied = 0
        for locale in LOCALES:
            if locale == DEFAULT_LOCALE:
                continue
            candidate = next(extract_dir.rglob(f"{locale}.json"), None)
            if candidate is None:
                print(f"Localization vendor sync: no {locale}.json in vendor bundle.")
                continue
            await asyncio.to_thread(shutil.copyfile, candidate, messages_dir / f"{locale}.json")
            copied += 1

    print(f"Localization vendor sync completed: updated {copied} locale catalogues.")
    return 0


def _request_lokalise_bundle_url(project_id: str, token: str) -> str:
    payload = json.dumps(
        {
            "format": "json",
            "original_filenames": False,
            "bundle_structure": "%LANG_ISO%.%FORMAT%",
            "filter_langs": [locale for locale in LOCALES if locale != DEFAULT_LOCALE],
            "export_empty_as": "base",
            "json_unescaped_slashes": True,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        LOKALISE_DOWNLOAD_URL.format(project_id=project_id),
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Api-Token": token,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body: Any = json.load(response)
    bundle_url = body.get("bundle_url") if isinstance(body, dict) else None
    if not isinstance(bundle_url, str) or not bundle_url:
        raise RuntimeError("Lokalise did not return a bundle_url.")
    return bundle_url


def _download_file(url: str, target: Path) -> None:
    with urllib.request.urlopen(url, timeout=120) as response:
        target.write_bytes(response.read())


async def async_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync localization catalogues from a vendor.")
    parser.add_argument("--vendor", default="lokalise", choices=["lokalise"])
    parser.add_argument("--project-id", default="")
    parser.add_argument("--token-ref", default=DEFAULT_TOKEN_REF)
    parser.add_argument("--messages-dir", type=Path, default=Path("../web/messages"))
    parser.add_argument("--secrets-file", default=".vault-secrets.json")
    args = parser.parse_args(argv)

    if args.vendor == "lokalise":
        return await sync_lokalise_catalogues(
            project_id=args.project_id,
            token_ref=args.token_ref,
            messages_dir=args.messages_dir,
            secrets_file=args.secrets_file,
        )
    raise AssertionError(f"unsupported vendor: {args.vendor}")


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
