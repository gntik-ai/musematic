from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def canonicalize_sbom(content: bytes | str | dict[str, Any] | list[Any]) -> str:
    """Return deterministic JSON used for stable SBOM hashes."""
    if isinstance(content, bytes):
        document = json.loads(content.decode("utf-8"))
    elif isinstance(content, str):
        document = json.loads(content)
    else:
        document = content
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_sha256(content: bytes | str) -> str:
    data = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(data).hexdigest()


def normalize_file(path: Path) -> dict[str, str]:
    canonical = canonicalize_sbom(path.read_bytes())
    return {
        "path": str(path),
        "content": canonical,
        "content_sha256": content_sha256(canonical),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize SBOM JSON documents.")
    parser.add_argument("paths", nargs="+", type=Path, help="SBOM JSON files")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional directory for canonicalized SBOM files",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results = [normalize_file(path) for path in args.paths]
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for result in results:
            source = Path(result["path"])
            target = args.output_dir / source.name
            target.write_text(result["content"], encoding="utf-8")
    print(json.dumps(results, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
