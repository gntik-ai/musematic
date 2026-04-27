from __future__ import annotations

from pathlib import Path
from platform.notifications.canonical import build_signature_headers, canonicalise_payload
from uuid import uuid4

import pytest


def test_documented_webhook_verification_snippet_round_trips_platform_signature() -> None:
    namespace: dict[str, object] = {}
    exec(_python_snippet(), namespace)
    verify = namespace["verify_musematic_signature"]

    body = canonicalise_payload({"event_type": "execution.failed", "payload": {"ok": True}})
    headers = build_signature_headers(
        webhook_id=uuid4(),
        payload=body,
        secret=b"shared-secret",
        idempotency_key=uuid4(),
        platform_version="test",
    )

    assert verify(headers, body, b"shared-secret", replay_window_seconds=86_400)
    with pytest.raises(ValueError, match="bad signature"):
        verify(headers, b'{"payload":{"ok":false}}', b"shared-secret", replay_window_seconds=86_400)


def _python_snippet() -> str:
    docs_path = Path(__file__).parents[5] / "docs/developer-guide/mcp-integration.md"
    markdown = docs_path.read_text()
    start = markdown.index("```python") + len("```python")
    end = markdown.index("```", start)
    return markdown[start:end].strip()
