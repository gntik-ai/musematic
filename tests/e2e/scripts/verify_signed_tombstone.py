#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a signed privacy tombstone export")
    parser.add_argument("signed_tombstone", type=Path)
    parser.add_argument("public_key_pem", nargs="?", type=Path)
    parser.add_argument(
        "--public-key",
        dest="public_key",
        help="Ed25519 public key PEM text, or a path to a PEM file.",
    )
    args = parser.parse_args()

    bundle = json.loads(args.signed_tombstone.read_text())
    canonical = bundle["tombstone"]
    tombstone = json.loads(canonical)
    proof_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    expected_hash = bundle.get("proof_hash", tombstone.get("proof_hash", proof_hash))
    if proof_hash != expected_hash:
        raise SystemExit("proof_hash mismatch")

    key = load_pem_public_key(_public_key_bytes(args))
    if not isinstance(key, Ed25519PublicKey):
        raise SystemExit("public key is not Ed25519")
    key.verify(base64.b64decode(bundle["signature"]), canonical.encode("utf-8"))
    print("signed tombstone verified")
    return 0


def _public_key_bytes(args: argparse.Namespace) -> bytes:
    if args.public_key:
        candidate = Path(args.public_key)
        if candidate.exists():
            return candidate.read_bytes()
        return args.public_key.encode("utf-8")
    if args.public_key_pem is None:
        raise SystemExit("public key PEM path or --public-key is required")
    return args.public_key_pem.read_bytes()


if __name__ == "__main__":
    raise SystemExit(main())
