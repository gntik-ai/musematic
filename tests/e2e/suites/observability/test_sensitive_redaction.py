from __future__ import annotations

import json
import time

import pytest

from suites.observability._helpers import log_lines, query_loki_until, unique_event

pytestmark = [pytest.mark.e2e, pytest.mark.observability, pytest.mark.asyncio]


def _create_redaction_pod(namespace: str, pod_name: str, line: str) -> None:
    try:
        from kubernetes import client, config
        from kubernetes.client import ApiException
    except ImportError as exc:  # pragma: no cover - depends on e2e extra installation
        pytest.skip(f"kubernetes client not installed: {exc}")

    try:
        config.load_kube_config()
    except Exception:
        try:
            config.load_incluster_config()
        except Exception as exc:
            pytest.skip(f"Kubernetes config unavailable: {exc}")

    api = client.CoreV1Api()
    pod = client.V1Pod(
        metadata=client.V1ObjectMeta(name=pod_name, labels={"app": "promtail-redaction-e2e"}),
        spec=client.V1PodSpec(
            restart_policy="Never",
            containers=[
                client.V1Container(
                    name="writer",
                    image="busybox:1.36",
                    command=["sh", "-c", f"echo '{line}'"],
                )
            ],
        ),
    )
    try:
        api.create_namespaced_pod(namespace, pod)
    except ApiException as exc:
        pytest.skip(f"Unable to create redaction pod in {namespace}: {exc}")


async def test_promtail_redacts_sensitive_patterns_before_loki(loki_client) -> None:
    namespace = "platform-control"
    event_id = unique_event("redaction")
    pod_name = f"redaction-{event_id[-10:]}"
    openai_key = "sk-" + "abcdefghijklmnopqrstuvwxyz" + "123456"
    api_key = "api_" + "key=" + "abcdefghijklmnopqrstuvwxyz"
    raw_message = (
        f"Bearer abc.def.ghi {openai_key} "
        f"{api_key} "
        "person@example.com 123-45-6789 4111 1111 1111 1111"
    )
    line = json.dumps(
        {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level": "error",
            "service": "redaction-e2e",
            "bounded_context": "observability_e2e",
            "message": f"{event_id} {raw_message}",
            "correlation_id": event_id,
        },
        separators=(",", ":"),
    )

    _create_redaction_pod(namespace, pod_name, line)
    streams = await query_loki_until(
        loki_client,
        '{service="redaction-e2e",bounded_context="observability_e2e",level="error"}',
        lambda result: any(event_id in row for stream in result for _ts, row in stream.get("values", [])),
        timeout=45.0,
    )
    payloads = [payload for _labels, payload in log_lines(streams) if payload.get("correlation_id") == event_id]
    assert payloads
    rendered = json.dumps(payloads[-1])
    assert "[REDACTED_TOKEN]" in rendered
    assert "[REDACTED_API_KEY]" in rendered
    assert "[REDACTED_EMAIL]" in rendered
    assert "[REDACTED_SSN]" in rendered
    assert "[REDACTED_CARD]" in rendered
    assert "person@example.com" not in rendered
    assert "123-45-6789" not in rendered
    assert "4111 1111 1111 1111" not in rendered
