#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

LANGUAGE_SAMPLES = {
    "Python": 'import requests\n\nresponse = requests.request("{method}", "{base_url}{path}", headers={{"Authorization": "Bearer $TOKEN"}})\nresponse.raise_for_status()\nprint(response.json())',
    "Go": 'req, _ := http.NewRequest("{method}", "{baseURL}{path}", nil)\nreq.Header.Set("Authorization", "Bearer "+token)\nresp, err := http.DefaultClient.Do(req)',
    "TypeScript": 'const response = await fetch(`${{baseUrl}}{path}`, {{\n  method: "{method}",\n  headers: {{ Authorization: `Bearer ${{token}}` }}\n}});',
    "curl": 'curl -X {method} "{base_url}{path}" -H "Authorization: Bearer $TOKEN"',
}


def _prepare_import_path(repo_root: Path) -> None:
    src = repo_root / "apps/control-plane/src"
    sys.path.insert(0, src.as_posix())
    module = sys.modules.get("platform")
    if module is not None and not hasattr(module, "__path__"):
        del sys.modules["platform"]


def _load_openapi(repo_root: Path) -> dict[str, Any]:
    _prepare_import_path(repo_root)
    from platform.main import create_app  # type: ignore[import-not-found]

    return create_app().openapi()


def _inject_code_samples(spec: dict[str, Any]) -> None:
    for path, operations in spec.get("paths", {}).items():
        if not isinstance(operations, dict):
            continue
        for method, operation in operations.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(operation, dict):
                continue
            operation["x-codeSamples"] = [
                {
                    "lang": language,
                    "source": template.format(
                        method=method.upper(),
                        path=path,
                        base_url="http://localhost:8000",
                        baseURL="{baseURL}",
                    ),
                }
                for language, template in LANGUAGE_SAMPLES.items()
            ]


def export_openapi(repo_root: Path, output: Path) -> dict[str, Any]:
    spec = _load_openapi(repo_root)
    _inject_code_samples(spec)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(spec, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return spec


def main() -> int:
    repo_root = Path.cwd()
    output = repo_root / "docs/api-reference/openapi.json"
    export_openapi(repo_root, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
