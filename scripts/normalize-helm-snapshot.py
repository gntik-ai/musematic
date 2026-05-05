#!/usr/bin/env python3
"""Normalize a rendered Helm template for the snapshot-diff CI gate.

Several subcharts (clickhouse, neo4j, qdrant, minio, redis) generate
Secret bodies with ``randAlphaNum`` fallbacks when they cannot
``lookup`` an existing in-cluster Secret. ``helm template`` runs
without an API server, so every render produces a fresh password —
which would make the committed snapshot diverge on every regeneration
and turn the snapshot-diff CI gate into noise.

This script reads a rendered Helm template on stdin and emits the same
content on stdout, with the volatile secret fields replaced by a
stable ``***SNAPSHOT-NORMALIZED***`` placeholder. The structural shape
of every Secret is preserved — additions, deletions, and renames of
keys still surface in the diff; only the random values are masked.

Volatile keys are matched by the (Secret-metadata.name, key) pair so
unrelated stringData entries (the ones a developer actually intends to
review) pass through unchanged.

Usage:
    helm template ... | scripts/normalize-helm-snapshot.py > snapshot.yaml
"""
from __future__ import annotations

import re
import sys

# (secret_name, key) → placeholder. The ``b64`` flavor masks neo4j's
# ``NEO4J_AUTH`` field which embeds the password into a "neo4j/<pw>"
# composite literal, and the simulation MinIO secret which embeds a
# random secret key into a credentials blob.
VOLATILE_FIELDS: dict[tuple[str, str], str] = {
    ("clickhouse-credentials", "CLICKHOUSE_PASSWORD"): "***SNAPSHOT-NORMALIZED***",
    ("neo4j-credentials", "NEO4J_PASSWORD"): "***SNAPSHOT-NORMALIZED***",
    ("neo4j-credentials", "NEO4J_AUTH"): "neo4j/***SNAPSHOT-NORMALIZED***",
    ("qdrant-api-key", "QDRANT_API_KEY"): "***SNAPSHOT-NORMALIZED***",
    ("minio-platform-credentials", "S3_SECRET_KEY"): "***SNAPSHOT-NORMALIZED***",
    ("minio-platform-credentials", "MINIO_SECRET_KEY"): "***SNAPSHOT-NORMALIZED***",
    ("minio-root-credentials", "MINIO_ROOT_PASSWORD"): "***SNAPSHOT-NORMALIZED***",
    ("minio-simulation-credentials", "MINIO_SECRET_KEY"): "***SNAPSHOT-NORMALIZED***",
}


# A minimal YAML-document iterator that doesn't pull in PyYAML so the
# script works in slim CI shells. Helm separates resources with a
# leading ``---`` line — split on that and process each chunk.
_DOC_SPLIT_RE = re.compile(r"^---\s*$", re.MULTILINE)
_NAME_RE = re.compile(r"^  name:\s*(.+?)\s*$", re.MULTILINE)
_KIND_RE = re.compile(r"^kind:\s*(.+?)\s*$", re.MULTILINE)


def _normalize_doc(doc: str) -> str:
    kind_match = _KIND_RE.search(doc)
    name_match = _NAME_RE.search(doc)
    if not (kind_match and name_match and kind_match.group(1) == "Secret"):
        return doc
    secret_name = name_match.group(1).strip().strip("'\"")
    fields_for_secret = {
        key: placeholder
        for (sn, key), placeholder in VOLATILE_FIELDS.items()
        if sn == secret_name
    }
    if not fields_for_secret:
        return doc

    # Replace every "  KEY: \"value\"" line where KEY is volatile.
    lines = doc.splitlines(keepends=True)
    multi_doc_neo4j_auth = False
    for i, line in enumerate(lines):
        for key, placeholder in fields_for_secret.items():
            # Match indented "KEY: <value>" with optional quoting.
            pattern = re.compile(
                rf'^(\s+){re.escape(key)}:\s*(["\']?).*?\2\s*$'
            )
            match = pattern.match(line.rstrip("\n"))
            if match:
                indent, quote = match.group(1), match.group(2) or "\""
                lines[i] = f"{indent}{key}: {quote}{placeholder}{quote}\n"
                if key == "NEO4J_AUTH":
                    multi_doc_neo4j_auth = True
                break

    # MinIO root credentials embed the password in a config.env literal
    # block — replace any "export MINIO_ROOT_PASSWORD=<random>" line.
    if secret_name == "minio-root-credentials":
        for i, line in enumerate(lines):
            if "MINIO_ROOT_PASSWORD=" in line and "export" in line:
                indent_end = len(line) - len(line.lstrip())
                lines[i] = (
                    f"{line[:indent_end]}export MINIO_ROOT_PASSWORD=***SNAPSHOT-NORMALIZED***\n"
                )

    return "".join(lines)


def _split_documents(text: str) -> list[str]:
    """Split YAML stream into documents preserving the ``---`` separators."""
    if not text:
        return []
    parts: list[str] = []
    cursor = 0
    for match in _DOC_SPLIT_RE.finditer(text):
        parts.append(text[cursor : match.start()])
        parts.append(match.group(0) + "\n")
        cursor = match.end() + 1
    parts.append(text[cursor:])
    return parts


def main() -> None:
    raw = sys.stdin.read()
    out_chunks = []
    for chunk in _split_documents(raw):
        if chunk.lstrip().startswith("---") or not chunk.strip():
            out_chunks.append(chunk)
            continue
        out_chunks.append(_normalize_doc(chunk))
    sys.stdout.write("".join(out_chunks))


if __name__ == "__main__":
    main()
