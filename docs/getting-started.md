# Getting Started

This page is the fastest path from a clean machine to a running musematic
control plane in local-dev mode. For production deployment see
[Installation](installation.md).

## Prerequisites

| Dependency | Version | Purpose |
|---|---|---|
| Python | 3.12+ | Control-plane runtime |
| Go | 1.25.x | Satellite services (reasoning, runtime, sandbox, simulation) |
| Node.js | 18+ | Frontend (`apps/web`) |
| pnpm | 9+ | Frontend workspace manager |
| Docker | 24+ | Local data stores |
| PostgreSQL | 16+ | System of record |
| Redis | 7+ | Hot state |
| Kafka | 3.7+ (KRaft) | Event bus |
| kubectl + kind | ≥ 1.28 / ≥ 0.23 | Only for the E2E test harness ([spec 071][s071]) |

The CI pipeline targets `ubuntu-latest-8-cores`. Local development works on
any Linux or macOS host with ≥ 16 GB RAM.

## 10-step local bring-up

Run each step from the repo root unless noted.

1. **Clone the repo.**
   ```bash
   git clone https://github.com/gntik-ai/musematic.git
   cd musematic
   ```

2. **Bring up data stores with Docker.**
   TODO(andrea): the repo does not currently ship a top-level
   `docker-compose.yml` for local-dev data stores. Use your own Postgres +
   Redis + Kafka + Qdrant + Neo4j + ClickHouse + OpenSearch + MinIO stack
   or the Helm chart under `deploy/helm/` against a kind cluster.

3. **Create a Python virtualenv and install control-plane deps.**
   ```bash
   cd apps/control-plane
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

4. **Run database migrations.**
   From the repo root (uses the `Makefile` at root):
   ```bash
   make migrate
   ```
   This runs `alembic -c apps/control-plane/migrations/alembic.ini upgrade head`.

5. **Configure environment.** At minimum set `POSTGRES_DSN`. All other
   settings have defaults suitable for local dev. See
   [Installation › Environment variables](installation.md#environment-variables)
   for the full reference.
   ```bash
   export POSTGRES_DSN="postgresql+asyncpg://postgres:postgres@localhost:5432/musematic"
   export REDIS_URL="redis://localhost:6379"
   export KAFKA_BROKERS="localhost:9092"
   ```

6. **Start the control-plane API.**
   ```bash
   cd apps/control-plane
   uvicorn src.platform.main:app --reload --port 8000
   ```

7. **Start the WebSocket hub** (separate process, uses the same codebase).
   ```bash
   PLATFORM_PROFILE=ws-hub uvicorn src.platform.main:app --port 8001
   ```

8. **Verify health.**
   ```bash
   curl http://localhost:8000/health
   curl http://localhost:8000/api/v1/openapi.json | jq '.info.title'
   ```
   You should see `"musematic"` or a similar title.

9. **Start the frontend.**
   ```bash
   cd apps/web
   pnpm install
   pnpm dev
   ```
   Open <http://localhost:3000/>.

10. **Create your first workspace.** Sign in (local mode creates a
    bootstrap admin; see [Administration › Enabling Features][feat]), then
    `POST /api/v1/workspaces` from the UI or via:
    ```bash
    curl -X POST http://localhost:8000/api/v1/workspaces \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"name": "my-first-workspace"}'
    ```

## Next steps

- Register an agent: [Agents](agents.md).
- Run a workflow: [Flows](flows.md).
- Review the admin surface: [Administration](administration/index.md).

[s071]: https://github.com/gntik-ai/musematic/tree/main/specs/071-e2e-kind-testing
[feat]: administration/enabling-features.md
