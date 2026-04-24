from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LLM_ENDPOINT_PATTERN = re.compile(r"/v1/(chat/completions|messages)\b")
ALLOWED_RELATIVE_PATHS = {
    Path("apps/control-plane/src/platform/common/clients/model_provider_http.py"),
    Path("apps/control-plane/src/platform/common/clients/model_router.py"),
    Path("apps/control-plane/src/platform/composition/llm/client.py"),
    Path("apps/control-plane/src/platform/evaluation/scorers/llm_judge.py"),
}


def find_violations(root: Path) -> list[tuple[Path, int, str]]:
    repo_root = root.resolve()
    source_root = repo_root / "apps/control-plane/src/platform"
    violations: list[tuple[Path, int, str]] = []
    for path in sorted(source_root.rglob("*.py")):
        rel_path = path.relative_to(repo_root)
        if rel_path in ALLOWED_RELATIVE_PATHS:
            continue
        text = path.read_text(encoding="utf-8")
        if "httpx" not in text:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if LLM_ENDPOINT_PATTERN.search(line):
                violations.append((rel_path, lineno, line.strip()))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail on new direct LLM provider HTTP calls outside the model router.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to the parent of ci/.",
    )
    args = parser.parse_args(argv)
    violations = find_violations(args.root)
    if not violations:
        return 0
    for path, lineno, line in violations:
        print(f"{path}:{lineno}: direct LLM endpoint call must route via ModelRouter: {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
