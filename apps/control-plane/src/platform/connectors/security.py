from __future__ import annotations

import hashlib
import hmac
import json
import warnings
from platform.common.config import PlatformSettings
from platform.common.secret_provider import MockSecretProvider
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


_VAULT_RESOLVER_DEPRECATION_EMITTED = False


class VaultResolver:
    def __init__(self, settings: PlatformSettings) -> None:
        global _VAULT_RESOLVER_DEPRECATION_EMITTED
        if not _VAULT_RESOLVER_DEPRECATION_EMITTED:
            warnings.warn(
                "`VaultResolver` is deprecated; use `platform.common.secret_provider` by v1.4.0.",
                DeprecationWarning,
                stacklevel=2,
            )
            _VAULT_RESOLVER_DEPRECATION_EMITTED = True
        self.settings = settings
        self._mock = MockSecretProvider(settings, validate_paths=False)

    def resolve(self, vault_path: str, credential_key: str) -> str:
        if self.settings.connectors.vault_mode == "mock":
            return self._resolve_mock(vault_path, credential_key)
        raise CredentialUnavailableError(credential_key)

    def _resolve_mock(self, vault_path: str, credential_key: str) -> str:
        return self._mock._get_sync(vault_path, credential_key)


def resolve_connector_secret(
    resolver: VaultResolver,
    vault_path: str,
    credential_key: str,
) -> str:
    return resolver.resolve(vault_path, credential_key)


def payload_to_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
