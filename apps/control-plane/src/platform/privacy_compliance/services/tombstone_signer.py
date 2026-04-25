from __future__ import annotations

from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


class TombstoneSigner:
    def __init__(self, signer: Any | None = None) -> None:
        self.signer = signer
        self._fallback_key = Ed25519PrivateKey.generate()

    async def sign(self, payload: bytes) -> bytes:
        sign = getattr(self.signer, "sign", None)
        if callable(sign):
            result = sign(payload)
            if hasattr(result, "__await__"):
                awaited = await result
                if isinstance(awaited, bytes):
                    return awaited
            elif isinstance(result, bytes):
                return result
            raise TypeError("Tombstone signer must return bytes")
        return self._fallback_key.sign(payload)

    async def current_key_version(self) -> str:
        version = getattr(self.signer, "current_key_version", None)
        if callable(version):
            result = version()
            if hasattr(result, "__await__"):
                return str(await result)
            return str(result)
        return "ephemeral-local"

    async def public_key_pem(self) -> str:
        public_key_pem = getattr(self.signer, "public_key_pem", None)
        if callable(public_key_pem):
            result = public_key_pem()
            if hasattr(result, "__await__"):
                result = await result
            if isinstance(result, bytes):
                return result.decode("ascii")
            return str(result)
        return self._fallback_key.public_key().public_bytes(
            Encoding.PEM,
            PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
