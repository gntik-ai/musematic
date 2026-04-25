from __future__ import annotations

from email.message import EmailMessage
from importlib import import_module
from platform.notifications.models import DeliveryOutcome, UserAlert
from typing import Any


class EmailDeliverer:
    async def send(
        self,
        alert: UserAlert,
        recipient_email: str,
        smtp_settings: dict[str, Any] | object,
    ) -> DeliveryOutcome:
        smtp_settings = _resolve_smtp_settings(smtp_settings)
        required = {"hostname", "port", "username", "password"}
        if not required.issubset(smtp_settings):
            return DeliveryOutcome.failed
        message = EmailMessage()
        message["From"] = smtp_settings.get("from_address") or smtp_settings["username"]
        message["To"] = recipient_email
        message["Subject"] = alert.title
        body = alert.body or alert.title
        if smtp_settings.get("email_format") == "html":
            message.set_content(body)
            message.add_alternative(f"<p>{body}</p>", subtype="html")
        else:
            message.set_content(body)
        aiosmtplib = import_module("aiosmtplib")
        try:
            await aiosmtplib.send(
                message,
                hostname=smtp_settings["hostname"],
                port=int(smtp_settings["port"]),
                username=smtp_settings["username"],
                password=smtp_settings["password"],
                start_tls=bool(smtp_settings.get("start_tls", True)),
            )
        except Exception:
            return DeliveryOutcome.failed
        return DeliveryOutcome.success


def _resolve_smtp_settings(settings_or_config: dict[str, Any] | object) -> dict[str, Any]:
    if isinstance(settings_or_config, dict):
        return settings_or_config
    extra = getattr(settings_or_config, "extra", None) or {}
    if not isinstance(extra, dict):
        return {}
    smtp_settings = extra.get("smtp_settings", extra)
    return smtp_settings if isinstance(smtp_settings, dict) else {}
