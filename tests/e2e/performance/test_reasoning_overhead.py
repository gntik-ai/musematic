from __future__ import annotations

import time
from pathlib import Path

import pytest

from performance.thresholds import REASONING_BASELINE_ITERATIONS, REASONING_OVERHEAD_MAX_MS
from suites._helpers import append_performance_measurement, post_json


@pytest.mark.asyncio
async def test_per_step_reasoning_overhead(http_client, mock_llm) -> None:
    sample_count = min(REASONING_BASELINE_ITERATIONS, 10)
    await mock_llm.set_responses({'agent_response': ['ok'] * sample_count * 2})
    started = time.perf_counter()
    for index in range(sample_count):
        await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': f'baseline {index}'})
    baseline_ms = (time.perf_counter() - started) * 1000 / sample_count

    started = time.perf_counter()
    for index in range(sample_count):
        await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': f'reasoning {index}', 'reasoning_mode': 'cot'})
    reasoning_ms = (time.perf_counter() - started) * 1000 / sample_count
    measured = max(0.0, reasoning_ms - baseline_ms)
    append_performance_measurement(Path('reports/performance.json'), test='test_per_step_reasoning_overhead', measured=measured, threshold=REASONING_OVERHEAD_MAX_MS, unit='milliseconds')
    assert measured < REASONING_OVERHEAD_MAX_MS
