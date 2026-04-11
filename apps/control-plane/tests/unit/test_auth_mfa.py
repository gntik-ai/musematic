from __future__ import annotations

import re
from platform.auth.mfa import (
    create_provisioning_uri,
    decrypt_secret,
    encrypt_secret,
    generate_recovery_codes,
    generate_totp_secret,
    verify_recovery_code,
    verify_totp_code,
)

import pyotp
import pytest
from cryptography.fernet import Fernet


def test_generate_totp_secret_and_verify_code() -> None:
    secret = generate_totp_secret()
    code = pyotp.TOTP(secret).now()

    assert re.fullmatch(r"[A-Z2-7]{32}", secret) is not None
    assert verify_totp_code(secret, code) is True
    assert verify_totp_code(secret, "000000") is False


def test_encrypt_and_decrypt_secret_roundtrip(auth_settings) -> None:
    encrypted = encrypt_secret("SECRET123", auth_settings.auth.mfa_encryption_key)

    assert decrypt_secret(encrypted, auth_settings.auth.mfa_encryption_key) == "SECRET123"

    with pytest.raises(ValueError, match="Invalid MFA encryption key or payload"):
        decrypt_secret(encrypted, Fernet.generate_key().decode("utf-8"))


def test_recovery_codes_and_provisioning_uri(auth_settings) -> None:
    raw_codes, hashed_codes = generate_recovery_codes()
    secret = generate_totp_secret()

    index = verify_recovery_code(raw_codes[0], hashed_codes)
    uri = create_provisioning_uri(secret, "user@example.com")

    assert len(raw_codes) == 10
    assert len(hashed_codes) == 10
    assert index == 0
    assert verify_recovery_code("INVALID123", hashed_codes) is None
    assert uri.startswith("otpauth://totp/Musematic:user%40example.com")
