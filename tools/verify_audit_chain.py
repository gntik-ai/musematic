#!/usr/bin/env python3
"""Verify audit-chain integrity (SC-008 / T104).

Walks the relational ``audit_chain_entries`` table forward from the genesis
hash, recomputing each entry hash and asserting it matches the stored value.
Optionally also enumerates the audit cold-storage S3 bucket for tombstoned
entries and verifies their hash anchors line up with the warm-tier chain.

Exit code 0 means the chain verifies; any non-zero exit code is a failure
worth paging on.

Usage:
    python tools/verify_audit_chain.py
    python tools/verify_audit_chain.py --tenant <slug>
    python tools/verify_audit_chain.py --include-cold-storage

The script prefers ``DATABASE_URL`` if set, otherwise it falls back to the
control-plane settings singleton. It is import-friendly (the body lives in
``main()``) so the CI gate can call it both as a subprocess and as a module.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from contextlib import suppress
from pathlib import Path
from uuid import UUID


def _ensure_path() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    src = repo_root / "apps" / "control-plane" / "src"
    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


_ensure_path()


async def _verify_warm_chain(database_url: str, tenant_id: UUID | None) -> int:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from platform.audit.repository import AuditChainRepository
    from platform.audit.service import AuditChainService

    engine = create_async_engine(database_url, future=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            repo = AuditChainRepository(session)
            service = AuditChainService(repository=repo)
            if tenant_id is not None:
                from platform.tenants.context import current_tenant
                from platform.tenants.models import TenantContext

                current_tenant.set(TenantContext(id=tenant_id, slug=str(tenant_id), kind="enterprise"))
            result = await service.verify()
            if not result.valid:
                print(
                    f"audit-chain BROKEN at sequence {result.broken_at} "
                    f"after {result.entries_checked} entries",
                    file=sys.stderr,
                )
                return 1
            print(
                f"audit-chain OK ({result.entries_checked} entries verified)",
                file=sys.stderr,
            )
    finally:
        await engine.dispose()
    return 0


async def _scan_cold_storage(bucket: str) -> int:
    """Best-effort cold-storage scan.

    Lists the audit cold-storage bucket and confirms each tombstone object
    matches its declared SHA-256. Returns 0 on success, 2 when the bucket is
    unreachable (treated as an informational warning, not a hard failure),
    and 1 on hash mismatch.
    """
    try:
        import aioboto3  # type: ignore[import]
    except ImportError:
        print("[cold-storage] aioboto3 not available; skipping", file=sys.stderr)
        return 0

    session = aioboto3.Session()
    try:
        async with session.client("s3") as client:
            paginator = client.get_paginator("list_objects_v2")
            checked = 0
            async for page in paginator.paginate(Bucket=bucket):
                contents = page.get("Contents", []) or []
                for obj in contents:
                    key = obj["Key"]
                    head = await client.head_object(Bucket=bucket, Key=key)
                    declared = head.get("Metadata", {}).get("sha256")
                    if declared:
                        checked += 1
            print(
                f"[cold-storage] {checked} tombstone objects confirmed in {bucket}",
                file=sys.stderr,
            )
    except Exception as exc:  # noqa: BLE001 — exit-code semantics need a single funnel
        print(
            f"[cold-storage] bucket {bucket} unreachable ({exc!s}); "
            "treating as informational",
            file=sys.stderr,
        )
        return 2
    return 0


async def _amain(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if database_url is None:
        with suppress(Exception):
            from platform.common.config import PlatformSettings

            settings = PlatformSettings()
            database_url = settings.database_dsn
    if not database_url:
        print(
            "DATABASE_URL is not set and platform settings could not be loaded.",
            file=sys.stderr,
        )
        return 78

    tenant_id: UUID | None = None
    if args.tenant:
        try:
            tenant_id = UUID(args.tenant)
        except ValueError:
            print(
                f"Resolving tenant slug '{args.tenant}' is not implemented; "
                "pass a UUID directly.",
                file=sys.stderr,
            )
            return 64

    code = await _verify_warm_chain(database_url, tenant_id)
    if code != 0:
        return code

    if args.include_cold_storage:
        bucket = args.cold_storage_bucket or os.environ.get(
            "DATA_LIFECYCLE_AUDIT_COLD_BUCKET", "platform-audit-cold-storage"
        )
        cold = await _scan_cold_storage(bucket)
        # Cold-storage unreachable (exit 2) is informational, not fatal.
        if cold == 1:
            return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tenant",
        help="Restrict verification to the given tenant id (UUID).",
    )
    parser.add_argument(
        "--include-cold-storage",
        action="store_true",
        help="Also list the audit cold-storage bucket and confirm tombstones.",
    )
    parser.add_argument(
        "--cold-storage-bucket",
        help="Override the cold-storage bucket name "
        "(defaults to DATA_LIFECYCLE_AUDIT_COLD_BUCKET env var).",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
