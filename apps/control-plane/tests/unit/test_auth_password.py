from __future__ import annotations

from platform.auth.password import hash_password, needs_rehash, verify_password

from argon2 import PasswordHasher


def test_hash_password_roundtrip() -> None:
    hashed = hash_password("SecureP@ss123")

    assert hashed.startswith("$argon2id$")
    assert verify_password("SecureP@ss123", hashed) is True


def test_verify_password_rejects_invalid_password() -> None:
    hashed = hash_password("SecureP@ss123")

    assert verify_password("wrong-password", hashed) is False


def test_needs_rehash_detects_legacy_parameters() -> None:
    legacy_hash = PasswordHasher(time_cost=2, memory_cost=1024, parallelism=2).hash("secret")

    assert needs_rehash(legacy_hash) is True


def test_needs_rehash_returns_true_for_invalid_hash() -> None:
    assert needs_rehash("not-a-valid-hash") is True
