from __future__ import annotations

import hashlib
from platform.common.middleware.tenant_resolver import _build_opaque_404_response

import pytest

pytestmark = pytest.mark.integration


def test_unknown_subdomain_responses_are_byte_identical() -> None:
    digests = set()
    for _ in range(100):
        response = _build_opaque_404_response()
        headers = b"\n".join(
            f"{key}:{value}".encode() for key, value in sorted(response.headers.items())
        )
        digests.add(hashlib.sha256(response.body + b"\n" + headers).hexdigest())

    assert len(digests) == 1
    assert "set-cookie" not in _build_opaque_404_response().headers
