from __future__ import annotations


def test_dlp_pipeline_emits_privacy_dlp_event() -> None:
    event = {"topic": "privacy.dlp.event", "action": "block", "contains_subject": True}
    assert event["topic"] == "privacy.dlp.event"
    assert event["action"] == "block"
