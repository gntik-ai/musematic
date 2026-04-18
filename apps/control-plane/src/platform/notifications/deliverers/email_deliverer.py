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
        smtp_settings: dict[str, Any],
    ) -> DeliveryOutcome:
        required = {"hostname", "port", "username", "password"}
        if not required.issubset(smtp_settings):
            return DeliveryOutcome.failed
        message = EmailMessage()
        message["From"] = smtp_settings.get("from_address") or smtp_settings["username"]
        message["To"] = recipient_email
        message["Subject"] = alert.title
        message.set_content(alert.body or alert.title)
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
