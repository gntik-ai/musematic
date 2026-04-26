from __future__ import annotations

from platform.common.clients.model_router import SecretProvider
from platform.multi_region_ops.models import RegionConfig
from platform.multi_region_ops.services.probes.base import ReplicationMeasurement
from typing import Any


class S3ReplicationProbe:
    component = "s3"

    def __init__(self, secret_provider: SecretProvider) -> None:
        self.secret_provider = secret_provider

    async def measure(
        self, *, source: RegionConfig, target: RegionConfig
    ) -> ReplicationMeasurement:
        del source
        bucket = target.endpoint_urls.get("s3_bucket")
        endpoint_ref = target.endpoint_urls.get("s3_endpoint_url_ref")
        access_key_ref = target.endpoint_urls.get("s3_access_key_ref")
        secret_key_ref = target.endpoint_urls.get("s3_secret_key_ref")
        if not isinstance(bucket, str) or not bucket:
            return ReplicationMeasurement(
                component=self.component,
                lag_seconds=None,
                health="unhealthy",
                error_detail="s3_bucket missing",
            )
        endpoint_url = await _secret_or_value(
            self.secret_provider, endpoint_ref, target.endpoint_urls.get("s3_endpoint_url")
        )
        access_key = await _secret_or_value(
            self.secret_provider, access_key_ref, target.endpoint_urls.get("s3_access_key")
        )
        secret_key = await _secret_or_value(
            self.secret_provider, secret_key_ref, target.endpoint_urls.get("s3_secret_key")
        )
        aioboto3 = __import__("aioboto3")
        session = aioboto3.Session()
        async with session.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        ) as client:
            replication = await client.get_bucket_replication(Bucket=bucket)
        lag_seconds = _extract_s3_lag(replication)
        return ReplicationMeasurement(
            component=self.component,
            lag_seconds=lag_seconds,
            health="healthy" if lag_seconds is not None and lag_seconds <= 60 else "degraded",
        )


async def _secret_or_value(
    secret_provider: SecretProvider,
    ref: Any,
    value: Any,
) -> str | None:
    if isinstance(ref, str) and ref:
        return await secret_provider.get_current(ref)
    return str(value) if value is not None else None


def _extract_s3_lag(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return 0
    metrics = payload.get("Metrics") or payload.get("metrics")
    if isinstance(metrics, dict):
        lag = metrics.get("ReplicationLatency") or metrics.get("replication_latency_seconds")
        if isinstance(lag, (int, float)):
            return int(lag)
    return 0
