from __future__ import annotations

from platform.auth.exceptions import OAuthStateInvalidError
from uuid import uuid4

import pytest
from tests.auth_oauth_support import build_oauth_service_fixture


def test_code_verifier_length_bounds_and_challenge_derivation(auth_settings) -> None:
    service, *_ = build_oauth_service_fixture(auth_settings)

    verifier = service._build_code_verifier()
    challenge = service._build_code_challenge(verifier)

    assert 43 <= len(verifier) <= 128
    assert verifier == verifier.strip()
    assert len(challenge) >= 43


def test_state_hmac_verification_and_tamper_detection(auth_settings) -> None:
    service, *_ = build_oauth_service_fixture(auth_settings)

    state = service._sign_state("nonce-123")

    assert service._verify_state(state) == "nonce-123"

    with pytest.raises(OAuthStateInvalidError):
        service._verify_state(state + "tampered")


def test_state_key_and_optional_uuid_parser(auth_settings) -> None:
    service, *_ = build_oauth_service_fixture(auth_settings)
    identifier = uuid4()

    assert service._state_key("abc") == "oauth:state:abc"
    assert service._parse_optional_uuid(str(identifier)) == identifier
    assert service._parse_optional_uuid(None) is None
