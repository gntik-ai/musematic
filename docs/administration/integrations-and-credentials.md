# Integrations & Credentials

Every external integration the platform touches requires admin-provisioned
credentials. This page inventories each integration, where its credentials
live, and how rotation works.

## The vault abstraction

Connector credentials go through a vault layer declared in
[`apps/control-plane/src/platform/connectors/security.py`][vault].
Backed by two modes:

| Mode | `VAULT_MODE` | Secret source |
|---|---|---|
| Mock (dev) | `mock` (default) | `.vault-secrets.json` file OR `CONNECTOR_SECRET_*` env vars. |
| HashiCorp Vault | `vault` | TODO(andrea): the Vault adapter is declared but raises `NotImplementedError` as of the current main branch. |

Secret name convention for mock mode:

```
CONNECTOR_SECRET_{CREDENTIAL_KEY}_{VAULT_PATH}
```

Example: a Slack connector with credential key `bot_token` stored at
vault path `slack/workspace-main` reads
`CONNECTOR_SECRET_BOT_TOKEN_SLACK_WORKSPACE_MAIN`.

## Connector types

Declared as an enum on `ConnectorType` in
[`apps/control-plane/src/platform/connectors/models.py`][cnn]. Currently
four types:

| Slug | Purpose | Credentials required |
|---|---|---|
| `slack` | Inbound mentions + outbound messages. | Bot/workspace token, signing secret. |
| `telegram` | Inbound + outbound via Bot API. | Bot token. |
| `email` | IMAP poll + SMTP send. | Host, port, username, password for each of IMAP and SMTP. |
| `webhook` | Generic outbound HTTP with HMAC signing. | HMAC secret (per webhook route). |

Configured via `POST /api/v1/connectors/instances`. Each instance stores
a reference to the vault path — the actual secret never touches
Postgres.

### Provisioning a Slack connector

```bash
# 1. Put the secret where the vault resolver can find it:
#    mock mode → .vault-secrets.json or env
#    real Vault → at path 'secret/data/slack/mycompany'

# 2. Register the connector instance
curl -X POST http://localhost:8000/api/v1/connectors/instances \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "connector_type": "slack",
    "workspace_id": "...",
    "name": "slack-mycompany",
    "credential_refs": {
      "bot_token":      "slack/mycompany#bot_token",
      "signing_secret": "slack/mycompany#signing_secret"
    }
  }'
```

The `credential_refs` map is resolved through the vault layer when the
connector worker starts — the secret never appears in the request, the
database, or the logs.

### Rotating credentials

1. Put the new secret at the same vault path (or with a new path).
2. Update the connector instance's `credential_refs` if the path changed.
3. Restart the connector worker pod. The route cache TTL
   (`CONNECTOR_ROUTE_CACHE_TTL_SECONDS`, default 60) means old cached
   routes flush within 60 seconds on their own.

## OAuth providers

OAuth 2.0 social login is handled by the `auth` bounded context. As of
the main branch, **no dedicated OAuth provider table exists**: OAuth
flows live in the journey tests under `tests/e2e/` and talk to mock
Google OIDC + GitHub OAuth servers (`services/mock-google-oidc/`,
`services/mock-github-oauth/`).

TODO(andrea): real Google + GitHub OAuth provider configuration is
called for by [spec 058][s058] (social login) but the production-side
admin API (`/api/v1/admin/oauth/providers`) and storage table are not
yet present in `apps/control-plane/src/platform/auth/`. The mock
servers demonstrate the shape expected by journey tests but are not
intended for production.

## LLM providers

The composition bounded context
([`apps/control-plane/src/platform/composition/llm/client.py`][llm])
calls an OpenAI-compatible HTTP API:

| Setting | Default | Purpose |
|---|---|---|
| `COMPOSITION_LLM_API_URL` | `http://localhost:8080/v1/chat/completions` | Chat-completions endpoint. |
| `COMPOSITION_LLM_MODEL` | `claude-opus-4-6` | Model identifier. |
| `COMPOSITION_LLM_TIMEOUT_SECONDS` | `25.0` | Request timeout. |
| `COMPOSITION_LLM_MAX_RETRIES` | `2` | Retry budget. |

There is **no multi-provider router** in the current codebase — one
endpoint per installation. TODO(andrea): the constitution's AD-19
("provider-agnostic model routing") is part of a planned audit-pass
update (`common/clients/model_router.py`) but the file is not yet in the
main branch.

For embeddings, the memory subsystem calls
`MEMORY_EMBEDDING_API_URL` (default
`http://localhost:8081/v1/embeddings`) using
`MEMORY_EMBEDDING_MODEL` (default `text-embedding-3-small`). The
registry uses `REGISTRY_EMBEDDING_API_URL` / `REGISTRY_EMBEDDING_VECTOR_SIZE`
similarly.

## SMTP / email

Email transport is delegated to a `notification_client` abstraction
invoked by the accounts bounded context for verification + invite
emails
([`apps/control-plane/src/platform/accounts/email.py`][acctsemail]). The
SMTP endpoint is configured outside the control plane.

TODO(andrea): the notification client's canonical env-var surface is
not documented in the current codebase — confirm whether SMTP settings
live in a `NotificationSettings` class (not found in `config.py` as of
this doc generation) or are injected via the admin UI in feature 027
(admin settings panel).

## Object storage (S3-compatible)

Any S3-compatible provider works — AWS S3, Hetzner, R2, Wasabi, MinIO.
The platform uses one set of env vars:

| Setting | Default | Purpose |
|---|---|---|
| `MINIO_ENDPOINT` | `http://localhost:9000` | S3 endpoint URL. |
| `MINIO_ACCESS_KEY` | `minioadmin` | Access key. |
| `MINIO_SECRET_KEY` | `minioadmin` | Secret key. |
| `MINIO_USE_SSL` | `false` | TLS toggle. |

(Naming pre-dates principle XVI — the `MINIO_*` prefix is a historical
label for the env var, not a required provider.)

Bucket allocations:

| Bucket (default) | Purpose |
|---|---|
| `platform-artifacts` (`MINIO_DEFAULT_BUCKET`) | General artifacts. |
| `agent-packages` (`REGISTRY_PACKAGE_BUCKET`) | Uploaded agent packages. |
| `context-assembly-records` (`CONTEXT_ENGINEERING_BUNDLE_BUCKET`) | Context bundles. |
| `trust-evidence` (`TRUST_EVIDENCE_BUCKET`) | Certification evidence. |
| `simulation-artifacts` (`SIMULATION_BUCKET`) | Simulation outputs. |
| `connector-dead-letters` (`MINIO_BUCKET_DEAD_LETTERS`) | DLQ archive. |

Rotate S3 credentials by updating the Helm values and restarting the
affected pods.

## Kubernetes

The runtime controller, sandbox manager, and simulation controller talk
to Kubernetes directly. Credentials come from:

- In-cluster service account (default — no setup required).
- `KUBECONFIG` env var (dev).

Service account RBAC requirements are set by the Helm chart under
`deploy/helm/platform/`.

[vault]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/src/platform/connectors/security.py
[cnn]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/src/platform/connectors/models.py
[llm]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/src/platform/composition/llm/client.py
[acctsemail]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/src/platform/accounts/email.py
[s058]: https://github.com/gntik-ai/musematic/tree/main/specs/058-oauth2-social-login
