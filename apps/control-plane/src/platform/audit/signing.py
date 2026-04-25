from __future__ import annotations

from platform.common.config import AuditSettings

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


class AuditChainSigning:
    def __init__(self, settings: AuditSettings) -> None:
        private_key_bytes = bytes.fromhex(settings.signing_key_hex)
        if len(private_key_bytes) != 32:
            raise ValueError("Audit signing key must be a 32-byte hex-encoded Ed25519 seed")
        self._private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
        self._public_key_hex = (
            settings.verifying_key_hex
            or self._private_key.public_key()
            .public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
            .hex()
        )

    @property
    def public_key_hex(self) -> str:
        return self._public_key_hex

    def current_key_version(self) -> str:
        return "1"

    def sign(self, document: bytes) -> bytes:
        return self._private_key.sign(document)

    def verify(self, document: bytes, signature: bytes, public_key_hex: str) -> bool:
        try:
            public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
            public_key.verify(signature, document)
            return True
        except Exception:
            return False
