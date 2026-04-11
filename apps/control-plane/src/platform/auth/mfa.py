from __future__ import annotations

import secrets
import string
from platform.auth.password import hash_password, verify_password
from typing import Final

import pyotp
from cryptography.fernet import Fernet, InvalidToken

_RECOVERY_ALPHABET: Final[str] = string.ascii_uppercase + string.digits
_RECOVERY_CODE_LENGTH: Final[int] = 8


def _fernet(key: str) -> Fernet:
    return Fernet(key.encode("utf-8"))


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def encrypt_secret(secret: str, key: str) -> str:
    return _fernet(key).encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_secret(encrypted: str, key: str) -> str:
    try:
        return _fernet(key).decrypt(encrypted.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Invalid MFA encryption key or payload") from exc


def create_provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(email, issuer_name="Musematic")


def verify_totp_code(secret: str, code: str) -> bool:
    return bool(pyotp.TOTP(secret).verify(code, valid_window=1))


def generate_recovery_codes(count: int = 10) -> tuple[list[str], list[str]]:
    raw_codes = [
        "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(_RECOVERY_CODE_LENGTH))
        for _ in range(count)
    ]
    return raw_codes, [hash_password(code) for code in raw_codes]


def verify_recovery_code(candidate: str, hashes: list[str]) -> int | None:
    for index, stored_hash in enumerate(hashes):
        if verify_password(candidate, stored_hash):
            return index
    return None

