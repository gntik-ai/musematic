#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))

    from platform.main import create_app

    app = create_app()
    spec = app.openapi()
    missing: list[str] = []

    for path, path_item in spec.get("paths", {}).items():
        if not path.startswith("/api/v1/admin/") and path != "/api/v1/admin":
            continue
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            tags = operation.get("tags", []) if isinstance(operation, dict) else []
            if "admin" not in tags:
                missing.append(f"{method.upper()} {path}")

    if missing:
        print("Admin OpenAPI tag verification failed:", file=sys.stderr)
        for operation in missing:
            print(f"  {operation} missing 'admin' tag", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
