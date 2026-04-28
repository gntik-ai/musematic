from __future__ import annotations

import time
from pathlib import Path

import pytest

from performance.thresholds import COLD_LAUNCH_MAX_SECONDS, WARM_LAUNCH_MAX_SECONDS
from suites._helpers import append_performance_measurement, post_json


@pytest.mark.asyncio
async def test_warm_and_cold_launch_latency(http_client) -> None:
    report = Path('reports/performance.json')
    await post_json(http_client, '/api/v1/runtime/warm-pool/fill', {'size': 2})
    started = time.perf_counter()
    await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': 'warm launch'})
    warm = time.perf_counter() - started
    append_performance_measurement(report, test='test_warm_launch', measured=warm, threshold=WARM_LAUNCH_MAX_SECONDS, unit='seconds')
    assert warm < WARM_LAUNCH_MAX_SECONDS

    await post_json(http_client, '/api/v1/runtime/warm-pool/drain', {})
    started = time.perf_counter()
    await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': 'cold launch'})
    cold = time.perf_counter() - started
    append_performance_measurement(report, test='test_cold_launch', measured=cold, threshold=COLD_LAUNCH_MAX_SECONDS, unit='seconds')
    assert cold < COLD_LAUNCH_MAX_SECONDS
