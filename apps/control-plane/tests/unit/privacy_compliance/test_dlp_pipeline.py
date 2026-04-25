from __future__ import annotations

from platform.privacy_compliance.dlp.scanner import DLPScanner
from platform.privacy_compliance.models import PrivacyDLPRule
from uuid import uuid4


def test_dlp_redacts_seeded_ssn_without_storing_raw_match() -> None:
    rule = PrivacyDLPRule(
        id=uuid4(),
        name="ssn_us",
        classification="pii",
        pattern=r"\b\d{3}-\d{2}-\d{4}\b",
        action="redact",
        enabled=True,
        seeded=True,
    )
    scanner = DLPScanner([rule])

    matches = scanner.scan("SSN 123-45-6789", None)
    result = scanner.apply_actions("SSN 123-45-6789", matches)

    assert result.output_text == "SSN [REDACTED:pii]"
    assert result.events[0].match_summary == "pii:ssn_us"
    assert "123-45-6789" not in result.events[0].match_summary


def test_dlp_luhn_filters_invalid_cards_and_blocks_valid_cards() -> None:
    rule = PrivacyDLPRule(
        id=uuid4(),
        name="credit_card",
        classification="financial",
        pattern=r"\b(?:\d[ -]*?){13,16}\b",
        action="block",
        enabled=True,
        seeded=True,
    )
    scanner = DLPScanner([rule])

    assert scanner.scan("not a card 1234567890123", None) == []
    text = "card 4242 4242 4242 4242"
    result = scanner.apply_actions(text, scanner.scan(text, None))

    assert result.blocked is True
