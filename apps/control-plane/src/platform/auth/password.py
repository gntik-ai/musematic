from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(plain: str) -> str:
    return _PASSWORD_HASHER.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bool(_PASSWORD_HASHER.verify(hashed, plain))
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return bool(_PASSWORD_HASHER.check_needs_rehash(hashed))
    except InvalidHashError:
        return True

