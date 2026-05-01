from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

from suites.ui_playwright import route_status_app_apis

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_webhook_subscription_form_and_hmac_contract(
    ui_page,
    platform_status_url: str,
) -> None:
    playwright_api = pytest.importorskip("playwright.async_api")
    await route_status_app_apis(ui_page)

    await ui_page.goto(f"{platform_status_url.rstrip('/')}/subscribe/")
    await ui_page.get_by_label("Webhook").check()
    await ui_page.get_by_label("Webhook URL").fill("https://receiver.example/status")
    await ui_page.get_by_label("Contact email").fill("ops@example.com")
    await ui_page.get_by_role("button", name="Subscribe").click()
    await playwright_api.expect(
        ui_page.get_by_text("Subscription request accepted").first,
    ).to_be_visible()

    body = json.dumps({"event_type": "status.subscription.test"}).encode()
    signature = base64.b64encode(
        hmac.new(b"status-page-dev-secret", body, hashlib.sha256).digest(),
    ).decode()

    assert hmac.compare_digest(
        signature,
        base64.b64encode(
            hmac.new(b"status-page-dev-secret", body, hashlib.sha256).digest(),
        ).decode(),
    )
