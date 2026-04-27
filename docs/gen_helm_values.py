from __future__ import annotations

import subprocess
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
content = subprocess.check_output(
    [sys.executable, "scripts/aggregate-helm-docs.py"],
    cwd=repo_root,
    text=True,
)

target = repo_root / "docs/configuration/helm-values.md"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(content, encoding="utf-8")
