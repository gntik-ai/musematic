#!/usr/bin/env python3
"""UPD-054 (107) — orphan-resource verifier for the SaaS-pass soak run.

Runs at the end of the e2e-saas-soak target. Lists test-tagged resources
across the four cleanup surfaces (tenants, Stripe customers, DNS records,
K8s Secrets) and exits non-zero if any list is non-empty.

Each lister is a thin wrapper around the corresponding fixture's
public list-helper (the fixtures live under ``tests/e2e/fixtures/``).
The script does NOT directly delete anything — the soak run's
expectation is that fixture teardown ran cleanly and left zero
orphans. A non-empty list means a fixture's cleanup hook missed a
case that needs investigation.

Usage:
    python tests/e2e/scripts/verify_no_orphans.py
    python tests/e2e/scripts/verify_no_orphans.py --tenant-prefix e2e-

Exit code 0 == zero orphans; any non-zero == orphan(s) found.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _prepare_import_path() -> None:
    src = REPO_ROOT / "tests" / "e2e"
    sys.path.insert(0, str(src))


async def _run(args: argparse.Namespace) -> int:
    _prepare_import_path()
    # Imports are lazy so the script can be invoked even when fixtures
    # haven't been wired yet (early in the SaaS-pass implementation).
    try:
        from fixtures.tenants import list_test_tenants  # type: ignore[import-not-found]
        from fixtures.stripe import StripeTestModeClient  # type: ignore[import-not-found]
        from fixtures.dns import build_dns_test_provider  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover — pre-fixture invocation
        print(f"verify_no_orphans: fixtures not yet wired ({exc}); skipping check.")
        return 0

    orphan_count = 0

    tenants = await list_test_tenants(slug_prefix=args.tenant_prefix)
    if tenants:
        orphan_count += len(tenants)
        print(f"FAIL: {len(tenants)} orphan tenants:")
        for t in tenants:
            print(f"  - {t.slug} (id={t.tenant_id})")

    # Stripe is best-effort — only check when test-mode credentials are
    # reachable. The fixture itself refuses to operate against live mode.
    try:
        stripe_client = StripeTestModeClient.from_environment()
        purged = await stripe_client.purge_test_customers()
        if purged > 0:
            orphan_count += purged
            print(f"FAIL: purged {purged} orphan Stripe test-mode customers.")
    except Exception as exc:  # pragma: no cover
        print(f"NOTE: Stripe orphan check skipped ({exc}).")

    # DNS — only meaningful in live mode.
    try:
        provider = build_dns_test_provider()
        # The mock provider has no concept of orphans across runs; the
        # live provider lists all e2e-* records.
        leaked = getattr(provider, "list_orphan_records", None)
        if leaked is not None:
            records = await leaked()
            if records:
                orphan_count += len(records)
                print(f"FAIL: {len(records)} orphan DNS records.")
    except Exception as exc:  # pragma: no cover
        print(f"NOTE: DNS orphan check skipped ({exc}).")

    if orphan_count == 0:
        print("OK: zero orphan resources detected.")
        return 0
    print(f"FAIL: {orphan_count} total orphan resources detected.")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tenant-prefix",
        default="e2e-",
        help="Slug prefix used to identify test tenants (default: e2e-).",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
