from __future__ import annotations

import argparse
import re
from pathlib import Path


PATTERNS = {
    "provider_api_key": re.compile(
        r"\b(?:sk-[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})\b"
    ),
    "raw_group_attribute_value": re.compile(
        r"\b(?:gender|ethnicity|race|religion)=['\"][^'\"]+['\"]"
    ),
    "pre_redaction_content": re.compile(r"original_content|pre_redaction_content"),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", default=["."])
    args = parser.parse_args()
    findings: list[str] = []
    for raw in args.paths:
        path = Path(raw)
        files = (
            [path]
            if path.is_file()
            else list(path.rglob("*.log")) + list(path.rglob("*.jsonl"))
        )
        for file_path in files:
            if not file_path.is_file():
                continue
            text = file_path.read_text(errors="ignore")
            for name, pattern in PATTERNS.items():
                if pattern.search(text):
                    findings.append(f"{file_path}: {name}")
    if findings:
        print("\n".join(findings))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
