from __future__ import annotations

import pyotp
import pytest

from suites._helpers import assert_status


@pytest.mark.asyncio
async def test_totp_enrollment_and_recovery_code(http_client) -> None:
    setup = assert_status(await http_client.get('/api/v1/auth/mfa/setup'))
    secret = setup.get('secret') or setup.get('totp_secret')
    assert secret, setup
    code = pyotp.TOTP(secret).now()
    verified = assert_status(await http_client.post('/api/v1/auth/mfa/verify', json={'code': code}))
    assert verified.get('enabled', True) is True

    invalid = await http_client.post('/api/v1/auth/mfa/verify', json={'code': '000000'})
    assert invalid.status_code == 401

    recovery_codes = verified.get('recovery_codes') or setup.get('recovery_codes') or []
    if recovery_codes:
        consumed = await http_client.post('/api/v1/auth/mfa/recovery', json={'code': recovery_codes[0]})
        assert consumed.status_code in {200, 202, 204}
