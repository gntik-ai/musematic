"""T029 — Integration test for ExportJobWorker.

Skip-marked scaffold. The actual test requires a live PostgreSQL
+ Kafka + S3 (MinIO) stack via ``make dev-up``.

The worker:
1. Subscribes to ``data_lifecycle.events``.
2. Filters to ``data_lifecycle.export.requested`` event type.
3. Acquires a Redis lease.
4. Drives ExportArchiver to assemble the ZIP.
5. Publishes via aioboto3 multipart upload to MinIO.
6. Generates a presigned URL with a 7-day TTL.
7. Updates the data_export_jobs row status to ``completed``.
8. Emits ``data_lifecycle.export.completed`` Kafka event.
9. Emits an audit-chain entry for the URL issuance.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="cluster integration test — requires make dev-up + live "
    "PostgreSQL + Kafka + MinIO. Tracked under tasks.md T029."
)


def test_placeholder() -> None:
    """Placeholder so pytest collection sees the file."""
