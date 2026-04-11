from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from platform.common.config import PlatformSettings
from platform.connectors.exceptions import CredentialUnavailableError, WebhookSignatureError
from typing import Any


def compute_hmac_sha256(secret: str, payload: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256)
    return digest.hexdigest()


def assert_webhook_signature(secret: str, payload: bytes, signature_header: str | None) -> None:
    if signature_header is None or not signature_header.startswith("sha256="):
        raise WebhookSignatureError("Missing X-Hub-Signature-256 header.")
    provided = signature_header.split("=", 1)[1]
    expected = compute_hmac_sha256(secret, payload)
    if not hmac.compare_digest(provided, expected):
        raise WebhookSignatureError()


def assert_slack_signature(
    secret: str,
    payload: bytes,
    signature_header: str | None,
    timestamp_header: str | None,
) -> None:
    if signature_header is None or timestamp_header is None:
        raise WebhookSignatureError("Missing Slack signature headers.")
    base = f"v0:{timestamp_header}:".encode() + payload
    expected = "v0=" + compute_hmac_sha256(secret, base)
    if not hmac.compare_digest(signature_header, expected):
        raise WebhookSignatureError("Slack signature is invalid.")


def scrub_secret_text(text: str | None, secrets: list[str]) -> str | None:
    if text is None:
        return None
    scrubbed = text
    for secret in secrets:
        if secret:
            scrubbed = scrubbed.replace(secret, "[REDACTED]")
    return scrubbed


class VaultResolver:
    def __init__(self, settings: PlatformSettings) -> None:
        self.settings = settings

    def resolve(self, vault_path: str, credential_key: str) -> str:
        if self.settings.connectors.vault_mode == "mock":
            return self._resolve_mock(vault_path, credential_key)
        raise CredentialUnavailableError(credential_key)

    def _resolve_mock(self, vault_path: str, credential_key: str) -> str:
        candidates = [Path(self.settings.connectors.vault_mock_secrets_file)]
        if not candidates[0].is_absolute():
            candidates.insert(
                0,
                Path.cwd() / self.settings.connectors.vault_mock_secrets_file,
            )
        for candidate in candidates:
            if not candidate.exists():
                continue
            content = json.loads(candidate.read_text(encoding="utf-8"))
            if isinstance(content, dict):
                value = content.get(vault_path)
                if isinstance(value, str):
                    return value
        env_key = "CONNECTOR_SECRET_" + "".join(
            char if char.isalnum() else "_"
            for char in f"{credential_key}_{vault_path}"
        ).upper()
        env_value = os.environ.get(env_key)
        if env_value is not None:
            return env_value
        raise CredentialUnavailableError(credential_key)


def payload_to_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
