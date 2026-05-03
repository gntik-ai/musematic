"""UPD-049 T055 — Acme with consume flag sees public agents in search.

See specs/099-marketplace-scope/spec.md and contracts/.

When wired against the live integration-test fixture this test MUST verify:

With consume_public_marketplace=true, an Acme user's marketplace search returns merged listings (tenant + public_default_tenant); response items include marketplace_scope so the UI can label public-source rows.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


def test_t055_placeholder() -> None:
    pytest.fail(
        "Replace with the live-fixture integration test described in the "
        "module docstring."
    )
