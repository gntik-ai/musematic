from __future__ import annotations

import time
from pathlib import Path

import pytest

from performance.thresholds import TRIVIAL_AGENT_ROUNDTRIP_MAX_SECONDS
from suites._helpers import append_performance_measurement, post_json, wait_for_state


@pytest.mark.asyncio
async def test_trivial_agent_roundtrip(http_client, mock_llm) -> None:
    await mock_llm.set_response('agent_response', 'ok')
    started = time.perf_counter()
    execution = await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': 'trivial'})
    await wait_for_state(http_client, f"/api/v1/executions/{execution['id']}", {'completed'})
    measured = time.perf_counter() - started
    append_performance_measurement(Path('reports/performance.json'), test='test_trivial_agent_roundtrip', measured=measured, threshold=TRIVIAL_AGENT_ROUNDTRIP_MAX_SECONDS, unit='seconds')
    assert measured < TRIVIAL_AGENT_ROUNDTRIP_MAX_SECONDS
