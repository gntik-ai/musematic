# Quickstart: WebSocket Real-Time Gateway (ws-hub)

**Feature**: 019-websocket-realtime-gateway  
**Date**: 2026-04-11

## Prerequisites

- Control plane running with auth + workspaces bounded contexts (features 014, 018)
- Kafka cluster running (feature 003)
- Python 3.12+ environment in `apps/control-plane/`

## Running the ws-hub Profile

```bash
# From apps/control-plane/
WS_CLIENT_BUFFER_SIZE=1000 \
WS_HEARTBEAT_INTERVAL_SECONDS=30 \
WS_HEARTBEAT_TIMEOUT_SECONDS=10 \
uvicorn apps.control-plane.entrypoints.ws_main:app --host 0.0.0.0 --port 8001
```

The ws-hub listens on port 8001 (separate from the REST API on port 8000).

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WS_CLIENT_BUFFER_SIZE` | `1000` | Per-connection event queue size |
| `WS_HEARTBEAT_INTERVAL_SECONDS` | `30` | Seconds between ping frames |
| `WS_HEARTBEAT_TIMEOUT_SECONDS` | `10` | Seconds to wait for pong before closing |
| `WS_MAX_MALFORMED_MESSAGES` | `10` | Malformed messages before closing connection |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker address |
| `DATABASE_URL` | (same as API) | Used only for auth service in-process calls |

## Manual Testing with wscat

Install: `npm install -g wscat`

```bash
# 1. Get a JWT token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password123"}' \
  | jq -r '.access_token')

# 2. Connect to WebSocket hub
wscat -c "ws://localhost:8001/ws" -H "Authorization: Bearer $TOKEN"

# 3. Subscribe to an execution channel
{"type": "subscribe", "channel": "execution", "resource_id": "7f3d9e1c-4a2b-4c8f-9d6e-2b1f5a3c7e90"}

# 4. List active subscriptions
{"type": "list_subscriptions"}

# 5. Unsubscribe
{"type": "unsubscribe", "channel": "execution", "resource_id": "7f3d9e1c-4a2b-4c8f-9d6e-2b1f5a3c7e90"}
```

## Running Tests

```bash
cd apps/control-plane

# Unit tests only (no Kafka/auth dependencies)
pytest tests/unit/test_ws_hub_*.py -v

# Integration tests (requires running Kafka + auth service)
pytest tests/integration/test_ws_hub_*.py -v

# Full suite
pytest tests/ -k "ws_hub" --asyncio-mode=auto -v
```

## Integration Test Scenarios

### Scenario 1: Authentication

```python
# test_ws_connection_flow.py
async def test_valid_token_connects(ws_client, valid_token):
    async with ws_client.connect(token=valid_token) as ws:
        msg = await ws.recv_json()
        assert msg["type"] == "connection_established"
        assert "connection_id" in msg

async def test_invalid_token_rejected(ws_client, invalid_token):
    with pytest.raises(ConnectionRefusedError):  # HTTP 401 → upgrade rejected
        async with ws_client.connect(token=invalid_token):
            pass
```

### Scenario 2: Subscription and Event Fan-out

```python
async def test_event_fanout_to_subscribed_clients(ws_client, kafka_producer, valid_token):
    async with ws_client.connect(token=valid_token) as ws:
        # Subscribe
        await ws.send_json({"type": "subscribe", "channel": "execution", "resource_id": "exec-123"})
        confirm = await ws.recv_json()
        assert confirm["type"] == "subscription_confirmed"
        
        # Produce event
        await kafka_producer.produce("workflow.runtime", execution_event(execution_id="exec-123"))
        
        # Verify delivery
        event_msg = await asyncio.wait_for(ws.recv_json(), timeout=0.5)
        assert event_msg["type"] == "event"
        assert event_msg["channel"] == "execution"
        assert event_msg["resource_id"] == "exec-123"
```

### Scenario 3: Backpressure

```python
async def test_slow_client_events_dropped(ws_client, kafka_producer, valid_token):
    # Set very small buffer for this test
    async with ws_client.connect(token=valid_token, buffer_size=3) as ws:
        await ws.subscribe("workspace", workspace_id)
        
        # Produce 10 events without reading
        for _ in range(10):
            await kafka_producer.produce("workspaces.events", workspace_event())
        
        # Now start reading — should see events_dropped
        messages = []
        async for msg in ws.receive_until_empty():
            messages.append(msg)
        
        types = [m["type"] for m in messages]
        assert "events_dropped" in types
```

### Scenario 4: Attention Auto-Subscription

```python
async def test_attention_auto_subscribed(ws_client, valid_token, user_id):
    async with ws_client.connect(token=valid_token) as ws:
        welcome = await ws.recv_json()
        assert welcome["type"] == "connection_established"
        auto_subs = welcome["auto_subscriptions"]
        assert any(s["channel"] == "attention" and s["resource_id"] == str(user_id)
                   for s in auto_subs)
```

## Kubernetes Deployment (ws-hub profile)

The ws-hub is deployed as a separate `Deployment` in the `platform-control` namespace:

```yaml
# deploy/helm/control-plane/templates/ws-hub-deployment.yaml
spec:
  replicas: 2
  selector:
    matchLabels:
      app: ws-hub
  template:
    spec:
      terminationGracePeriodSeconds: 30
      containers:
      - name: ws-hub
        args: ["ws_hub"]           # runtime profile selector in ws_main.py
        ports:
        - containerPort: 8001
        env:
        - name: WS_CLIENT_BUFFER_SIZE
          value: "1000"
```

The load balancer must be configured for **sticky sessions** (or clients must handle transparent reconnection) because connection state is in-memory per-instance. The frontend `lib/ws.ts` already handles reconnection with exponential backoff.
