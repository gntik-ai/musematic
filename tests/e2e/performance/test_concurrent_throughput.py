from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from performance.thresholds import CONCURRENT_EXECUTION_COUNT, CONCURRENT_MAX_WALL_CLOCK_SECONDS
from suites._helpers import append_performance_measurement, post_json, wait_for_state


@pytest.mark.asyncio
async def test_10_concurrent_executions_complete_within_threshold(http_client, mock_llm) -> None:
    await mock_llm.set_responses({'agent_response': ['ok'] * CONCURRENT_EXECUTION_COUNT})
    started = time.perf_counter()
    executions = await asyncio.gather(*(post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': f'concurrent {idx}'}) for idx in range(CONCURRENT_EXECUTION_COUNT)))
    finals = await asyncio.gather(*(wait_for_state(http_client, f"/api/v1/executions/{execution['id']}", {'completed'}) for execution in executions))
    measured = time.perf_counter() - started
    assert all(item.get('state') == 'completed' for item in finals)
    append_performance_measurement(Path('reports/performance.json'), test='test_10_concurrent', measured=measured, threshold=CONCURRENT_MAX_WALL_CLOCK_SECONDS, unit='seconds')
    assert measured < CONCURRENT_MAX_WALL_CLOCK_SECONDS
