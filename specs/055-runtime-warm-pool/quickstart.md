# Quickstart & Test Scenarios: Runtime Warm Pool and Secrets Injection

**Feature**: `specs/055-runtime-warm-pool/spec.md`
**Date**: 2026-04-18

---

## Setup Prerequisites

```python
# Fixtures assumed for all scenarios
WORKSPACE_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
AGENT_TYPE   = "python-3.12"
AGENT_FQN    = "acme/agent/test-agent@v1"

# Prometheus metrics helper
metrics = Metrics(prometheus_client.CollectorRegistry())

# gRPC server with pgx mock
server = RuntimeControlServer(db=mock_pgx_conn, manager=WarmPoolManager(), metrics=metrics)
```

---

## Scenario 1 — Warm pool metrics: available gauge set after pod registers

```python
metrics.SetWarmPoolAvailable(str(WORKSPACE_ID), AGENT_TYPE, 3.0)
gauge = metrics._warm_pool_available.labels(workspace_id=str(WORKSPACE_ID), agent_type=AGENT_TYPE)
assert gauge._value.get() == 3.0
```

---

## Scenario 2 — Warm dispatch latency histogram recorded

```python
metrics.ObserveWarmDispatchLatency(str(WORKSPACE_ID), AGENT_TYPE, 450.0)
hist = metrics._warm_dispatch_latency_ms.labels(workspace_id=str(WORKSPACE_ID), agent_type=AGENT_TYPE)
assert hist._sum.get() == 450.0
```

---

## Scenario 3 — Cold start counter increments on pool miss

```python
metrics.IncColdStart(str(WORKSPACE_ID), AGENT_TYPE)
metrics.IncColdStart(str(WORKSPACE_ID), AGENT_TYPE)
counter = metrics._cold_start_count_total.labels(workspace_id=str(WORKSPACE_ID), agent_type=AGENT_TYPE)
assert counter._value.get() == 2.0
```

---

## Scenario 4 — WarmPoolConfig persists target via upsert

```python
req = WarmPoolConfigRequest(workspace_id=str(WORKSPACE_ID), agent_type=AGENT_TYPE, target_size=5)
resp = await server.WarmPoolConfig(req, context=mock_ctx)
assert resp.accepted is True
mock_pgx_conn.assert_upsert_called_with(
    "runtime_warm_pool_targets",
    workspace_id=str(WORKSPACE_ID), agent_type=AGENT_TYPE, target_size=5
)
```

---

## Scenario 5 — WarmPoolStatus returns live counts from manager

```python
manager.RegisterReadyPod(f"{WORKSPACE_ID}/{AGENT_TYPE}", "pod-abc")
req = WarmPoolStatusRequest(workspace_id=str(WORKSPACE_ID), agent_type=AGENT_TYPE)
resp = await server.WarmPoolStatus(req, context=mock_ctx)
assert len(resp.keys) == 1
assert resp.keys[0].available_count == 1
assert resp.keys[0].target_size == 5  # from mock DB row
```

---

## Scenario 6 — WarmPoolConfig rejects negative target_size

```python
req = WarmPoolConfigRequest(workspace_id=str(WORKSPACE_ID), agent_type=AGENT_TYPE, target_size=-1)
with pytest.raises(grpc.RpcError) as exc:
    await server.WarmPoolConfig(req, context=mock_ctx)
assert exc.value.code() == grpc.StatusCode.INVALID_ARGUMENT
```

---

## Scenario 7 — Python client warm_pool_status delegates to gRPC

```python
client = RuntimeControllerClient()
client.stub = mock_stub  # mock returning WarmPoolStatusResponse with 2 keys
result = await client.warm_pool_status(workspace_id=str(WORKSPACE_ID))
assert len(result["keys"]) == 2
mock_stub.WarmPoolStatus.assert_called_once()
```

---

## Scenario 8 — Python client warm_pool_config delegates to gRPC

```python
result = await client.warm_pool_config(str(WORKSPACE_ID), AGENT_TYPE, 5)
assert result["accepted"] is True
mock_stub.WarmPoolConfig.assert_called_once_with(
    WarmPoolConfigRequest(workspace_id=str(WORKSPACE_ID), agent_type=AGENT_TYPE, target_size=5)
)
```

---

## Scenario 9 — launch_runtime sends prefer_warm=True by default

```python
payload = {"execution_id": str(uuid4()), "agent_fqn": AGENT_FQN}
await client.launch_runtime(payload)
mock_stub.LaunchRuntime.assert_called_once()
call_args = mock_stub.LaunchRuntime.call_args[0][0]
assert call_args.prefer_warm is True
```

---

## Scenario 10 — Scheduler dispatch passes prefer_warm; warm_start=True recorded

```python
scheduler = SchedulerService(..., runtime_controller=mock_runtime_controller)
mock_runtime_controller.launch_runtime.return_value = {"warm_start": True}
await scheduler._dispatch_to_runtime(execution, step)
mock_runtime_controller.launch_runtime.assert_called_once()
args = mock_runtime_controller.launch_runtime.call_args
assert args[1]["prefer_warm"] is True
```

---

## Scenario 11 — GET /api/v1/runtime/warm-pool/status returns 200 for admin

```python
resp = await async_client.get(
    "/api/v1/runtime/warm-pool/status",
    headers={"Authorization": f"Bearer {admin_token}"}
)
assert resp.status_code == 200
data = resp.json()
assert "keys" in data
```

---

## Scenario 12 — GET /api/v1/runtime/warm-pool/status returns 403 for non-admin

```python
resp = await async_client.get(
    "/api/v1/runtime/warm-pool/status",
    headers={"Authorization": f"Bearer {member_token}"}
)
assert resp.status_code == 403
```

---

## Scenario 13 — PUT /api/v1/runtime/warm-pool/config returns 200

```python
resp = await async_client.put(
    "/api/v1/runtime/warm-pool/config",
    json={"workspace_id": str(WORKSPACE_ID), "agent_type": AGENT_TYPE, "target_size": 5},
    headers={"Authorization": f"Bearer {admin_token}"}
)
assert resp.status_code == 200
assert resp.json()["accepted"] is True
```

---

## Scenario 14 — PUT /api/v1/runtime/warm-pool/config returns 422 for negative target

```python
resp = await async_client.put(
    "/api/v1/runtime/warm-pool/config",
    json={"workspace_id": str(WORKSPACE_ID), "agent_type": AGENT_TYPE, "target_size": -1},
    headers={"Authorization": f"Bearer {admin_token}"}
)
assert resp.status_code == 422
```

---

## Scenario 15 — Prompt preflight blocks dispatch on bearer token

```python
payload = {"prompt_context": "Authorization: Bearer sk-abc123456789"}
with pytest.raises(PolicySecretLeakError) as exc:
    await scheduler._prompt_secret_preflight(payload, execution=execution, step=step)
assert exc.value.secret_type == "bearer_token"
mock_producer.publish.assert_called_once()
event = mock_producer.publish.call_args[0][0]
assert event["event_type"] == "prompt_secret_detected"
assert event["data"]["secret_type"] == "bearer_token"
```

---

## Scenario 16 — Prompt preflight passes clean prompt

```python
clean_payload = {"prompt_context": "What is the capital of France?"}
await scheduler._prompt_secret_preflight(clean_payload, execution=execution, step=step)
mock_producer.publish.assert_not_called()
# No exception raised — dispatch proceeds
```

---

## Scenario 17 — Prompt preflight recognizes all 5 secret types

```python
patterns = [
    ("bearer_token", "Bearer eyJabc123456789"),
    ("api_key", "sk-AbcDef123456789"),
    ("jwt_token", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.abc123"),
    ("connection_string", "postgres://user:pass@host:5432/db"),
    ("password_literal", "password=MySecret123"),
]
for expected_type, secret_text in patterns:
    payload = {"context": secret_text}
    with pytest.raises(PolicySecretLeakError) as exc:
        await scheduler._prompt_secret_preflight(payload, execution=execution, step=step)
    assert exc.value.secret_type == expected_type
```

---

## Scenario 18 — Cold start fallback when pool is empty (FR-005)

```python
mock_runtime_controller.launch_runtime.return_value = {"warm_start": False}
# Should succeed — no exception raised, warm_start=False is valid
await scheduler._dispatch_to_runtime(execution, step)
mock_runtime_controller.launch_runtime.assert_called_once()
```

---

## Scenario 19 — Alembic migration 043 creates table and unique constraint

```python
# Alembic upgrade test using real SQLite or PostgreSQL test DB
run_migrations_up_to("043_runtime_warm_pool_targets")
assert table_exists("runtime_warm_pool_targets")
assert unique_constraint_exists("runtime_warm_pool_targets", ["workspace_id", "agent_type"])
# Downgrade
run_migrations_down_to("042_prescreener_guardrail_layer")
assert not table_exists("runtime_warm_pool_targets")
```
