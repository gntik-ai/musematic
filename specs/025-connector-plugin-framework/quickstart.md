# Quickstart: Connector Plugin Framework

**Branch**: `025-connector-plugin-framework` | **Date**: 2026-04-11

## Prerequisites

Services required (from `deploy/helm/`):
- PostgreSQL (CloudNativePG) — `make deploy-postgres`
- Redis (Bitnami cluster) — `make deploy-redis`
- Kafka (Strimzi) — `make deploy-kafka`
- MinIO — `make deploy-minio`

A vault service (or mock) must be available for credential resolution. For local dev, set `VAULT_MODE=mock` in `.env` to use a local secrets file instead of a real vault.

Python dependencies (additional for this feature):
```
aioimaplib>=1.0   # Email inbound (IMAP)
aiosmtplib>=3.0   # Email outbound (SMTP)
```

## Running the API

```bash
cd apps/control-plane

# Run migrations
alembic upgrade head

# Seed connector types (one-time)
python -m platform.connectors.seed

# Start API profile
python entrypoints/api_main.py
```

## Running the Connector Worker

The connector worker consumes `connector.delivery` and runs the email polling scheduler:

```bash
cd apps/control-plane
python entrypoints/worker_main.py
```

Worker environment variables:
```bash
CONNECTOR_WORKER_ENABLED=true
EMAIL_POLL_INTERVAL_SECONDS=60  # Default
CONNECTOR_DELIVERY_MAX_CONCURRENT=10
```

## Running Tests

```bash
cd apps/control-plane

# Unit tests only (no external services needed)
pytest tests/unit/ -v

# Integration tests (requires PostgreSQL, Redis, Kafka, MinIO)
pytest tests/integration/ -v

# Full suite
pytest tests/ -v --cov=src/platform/connectors --cov-report=term-missing
```

## Test Scenarios

### Scenario 1 — Create and Configure a Slack Connector

```python
# 1. List connector types
GET /api/v1/connectors/types
# → see "slack" type with its config schema

# 2. Create a Slack connector instance
POST /api/v1/workspaces/{ws_id}/connectors
{
  "connector_type_slug": "slack",
  "name": "Engineering Slack",
  "config": {
    "team_id": "T12345",
    "default_channel": "C98765",
    "bot_token": {"$ref": "bot_token"},
    "signing_secret": {"$ref": "signing_secret"}
  },
  "credential_refs": {
    "bot_token": "workspaces/{ws_id}/connectors/{c_id}/bot_token",
    "signing_secret": "workspaces/{ws_id}/connectors/{c_id}/signing_secret"
  }
}
# → 201 Created, status: "enabled"

# 3. Run health check
POST /api/v1/workspaces/{ws_id}/connectors/{c_id}/health-check
# → {"status": "healthy", "latency_ms": 120.5}

# 4. Create a routing rule
POST /api/v1/workspaces/{ws_id}/connectors/{c_id}/routes
{
  "name": "Support channel → triage",
  "channel_pattern": "#support*",
  "target_agent_fqn": "support-ops:triage-agent",
  "priority": 10
}
```

### Scenario 2 — Inbound Slack Message Flow

```bash
# Simulate a Slack Events API call
curl -X POST http://localhost:8000/api/v1/inbound/slack/{connector_id} \
  -H "X-Slack-Signature: v0=<hmac_sha256_signature>" \
  -H "X-Slack-Request-Timestamp: 1712846400" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "event_callback",
    "event": {
      "type": "message",
      "text": "I need help with my order",
      "user": "U123456",
      "channel": "C-support-general",
      "ts": "1712846400.000000"
    }
  }'
# → 200 {"ok": true}
# → InboundMessage published to connector.ingress topic
```

Verify the message was published:
```bash
# Consume one message from connector.ingress
kafka-console-consumer.sh --topic connector.ingress --from-beginning --max-messages 1
```

### Scenario 3 — Outbound Delivery with Retry

```python
# 1. Create an outbound delivery
POST /api/v1/workspaces/{ws_id}/deliveries
{
  "connector_instance_id": "{c_id}",
  "destination": "C-support-general",
  "content_text": "Your ticket #1234 has been created.",
  "priority": 50
}
# → 201 Created, status: "pending"

# 2. Worker picks up and processes (watch worker logs)
# → status changes to "delivered" or "failed" (if Slack API unreachable)

# 3. Simulate failures beyond max_attempts
# Configure connector with invalid credentials → worker will fail delivery
# After 3 attempts: status → "dead_lettered"

# 4. Inspect DLQ
GET /api/v1/workspaces/{ws_id}/dead-letter?connector_id={c_id}
# → shows entry with full error_history

# 5. Redeliver
POST /api/v1/workspaces/{ws_id}/dead-letter/{entry_id}/redeliver
# → new OutboundDelivery created
```

### Scenario 4 — Credential Isolation

```python
# Verify credentials are never exposed in API responses
GET /api/v1/workspaces/{ws_id}/connectors/{c_id}
# → config.bot_token == {"$ref": "bot_token"}  ← NOT the actual token
# → no credential_refs.vault_path in response (masked)

# Verify cross-workspace access denied
GET /api/v1/workspaces/{other_ws_id}/connectors/{c_id}
# → 404 Not Found
```

### Scenario 5 — Webhook Connector with Signature Verification

```bash
# Create a webhook connector
POST /api/v1/workspaces/{ws_id}/connectors
{
  "connector_type_slug": "webhook",
  "name": "GitHub Webhooks",
  "config": {
    "signing_secret": {"$ref": "signing_secret"}
  },
  "credential_refs": {
    "signing_secret": "workspaces/{ws_id}/connectors/{c_id}/signing_secret"
  }
}

# Send a valid signed webhook
BODY='{"action": "opened", "issue": {...}}'
SECRET='my-signing-secret'
SIGNATURE="sha256=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | cut -d' ' -f2)"

curl -X POST http://localhost:8000/api/v1/inbound/webhook/{c_id} \
  -H "X-Hub-Signature-256: $SIGNATURE" \
  -H "Content-Type: application/json" \
  -d "$BODY"
# → 200 {"received": true}

# Send with invalid signature
curl -X POST http://localhost:8000/api/v1/inbound/webhook/{c_id} \
  -H "X-Hub-Signature-256: sha256=invalid" \
  -d '{"action": "opened"}'
# → 401 {"error": "webhook_signature_invalid"}
```

### Scenario 6 — Email Connector Polling

```python
# Create an email connector
POST /api/v1/workspaces/{ws_id}/connectors
{
  "connector_type_slug": "email",
  "name": "Support Inbox",
  "config": {
    "imap_host": "imap.example.com",
    "imap_port": 993,
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
    "email_address": "support@example.com",
    "imap_password": {"$ref": "imap_password"},
    "smtp_password": {"$ref": "smtp_password"},
    "poll_interval_seconds": 60,
    "inbox_folder": "INBOX"
  },
  "credential_refs": {
    "imap_password": "workspaces/{ws_id}/connectors/{c_id}/imap_password",
    "smtp_password": "workspaces/{ws_id}/connectors/{c_id}/smtp_password"
  }
}
# Worker will poll INBOX every 60s and normalize new emails to InboundMessage
```

## Environment Variables

```bash
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://...

# Redis
REDIS_NODES=musematic-redis-cluster.platform-data:6379

# Kafka
KAFKA_BOOTSTRAP_SERVERS=musematic-kafka:9092
CONNECTOR_INGRESS_TOPIC=connector.ingress
CONNECTOR_DELIVERY_TOPIC=connector.delivery

# MinIO (for DLQ archival)
MINIO_ENDPOINT=http://minio:9000
MINIO_BUCKET_DEAD_LETTERS=connector-dead-letters

# Vault (mock for local dev)
VAULT_MODE=mock                          # "mock" or "vault"
VAULT_MOCK_SECRETS_FILE=.vault-secrets.json

# Connector worker settings
CONNECTOR_DELIVERY_CONSUMER_GROUP=connector-delivery-worker
CONNECTOR_RETRY_SCAN_INTERVAL_SECONDS=30
CONNECTOR_ROUTE_CACHE_TTL_SECONDS=60
CONNECTOR_MAX_PAYLOAD_SIZE_BYTES=1048576  # 1 MB
```
