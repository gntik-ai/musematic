"""MinIO diagnostic check."""

from __future__ import annotations

from time import perf_counter

from platform_cli.constants import ComponentCategory
from platform_cli.models import CheckStatus, DiagnosticCheck


class MinIOCheck:
    """Verify MinIO access by checking one bucket."""

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str = "platform-backups",
    ) -> None:
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.name = "minio"

    async def run(self) -> DiagnosticCheck:
        import aioboto3

        started = perf_counter()
        session = aioboto3.Session()
        try:
            async with session.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            ) as client:
                await client.head_bucket(Bucket=self.bucket)
        except Exception as exc:
            return DiagnosticCheck(
                component="minio",
                display_name="MinIO",
                category=ComponentCategory.DATA_STORE,
                status=CheckStatus.UNHEALTHY,
                error=str(exc),
                remediation="Check MinIO endpoint, credentials, and bucket existence.",
            )
        latency_ms = round((perf_counter() - started) * 1000, 2)
        return DiagnosticCheck(
            component="minio",
            display_name="MinIO",
            category=ComponentCategory.DATA_STORE,
            status=CheckStatus.HEALTHY,
            latency_ms=latency_ms,
        )
