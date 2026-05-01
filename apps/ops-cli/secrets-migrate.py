#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy Vault secrets to default tenant paths.")
    parser.add_argument("--addr", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--env", required=True, choices=["production", "staging", "dev", "test", "ci"])
    parser.add_argument("--mount", default="secret")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        import hvac  # type: ignore[import-untyped]
    except Exception:
        print("hvac is required to run this utility", file=sys.stderr)
        return 2

    client = hvac.Client(url=args.addr, token=args.token)
    if not client.is_authenticated():
        print("Vault authentication failed", file=sys.stderr)
        return 2

    legacy_root = f"musematic/{args.env}"
    migrated = 0
    for legacy_path in _walk_kv2(client, args.mount, legacy_root):
        relative = legacy_path.removeprefix(f"{legacy_root}/")
        domain, _, resource = relative.partition("/")
        if not domain or not resource or domain in {"tenants", "_platform"}:
            continue
        target_path = f"musematic/{args.env}/tenants/default/{domain}/{resource}"
        if args.dry_run:
            print(f"{legacy_path} -> {target_path}")
            migrated += 1
            continue
        value = client.secrets.kv.v2.read_secret_version(
            mount_point=args.mount,
            path=legacy_path,
        )["data"]["data"]
        client.secrets.kv.v2.create_or_update_secret(
            mount_point=args.mount,
            path=target_path,
            secret=value,
        )
        observed = client.secrets.kv.v2.read_secret_version(
            mount_point=args.mount,
            path=target_path,
        )["data"]["data"]
        if observed != value:
            print(f"verification failed for {target_path}", file=sys.stderr)
            return 1
        print(f"copied {legacy_path} -> {target_path}")
        migrated += 1
    print(f"migrated={migrated}")
    return 0


def _walk_kv2(client: Any, mount: str, root: str) -> list[str]:
    found: list[str] = []
    stack = [root.rstrip("/") + "/"]
    while stack:
        current = stack.pop()
        try:
            response = client.secrets.kv.v2.list_secrets(mount_point=mount, path=current)
        except Exception:
            leaf = current.rstrip("/")
            if leaf:
                found.append(leaf)
            continue
        for key in response["data"].get("keys", []):
            if key.endswith("/"):
                stack.append(f"{current}{key}")
            else:
                found.append(f"{current}{key}")
    return found


if __name__ == "__main__":
    raise SystemExit(main())
