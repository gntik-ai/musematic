# Data Model: MCP Integration

**Feature**: 066-mcp-integration | **Date**: 2026-04-19  
**Spec**: [spec.md](spec.md) | **Research**: [research.md](research.md)

---

## New Tables

### `mcp_server_registrations`

Operator-controlled registry of approved external MCP endpoints per workspace.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `workspace_id` | UUID | FK → workspaces, NOT NULL | |
| `display_name` | VARCHAR(255) | NOT NULL | Human-readable label |
| `endpoint_url` | VARCHAR(2048) | NOT NULL | HTTPS only (FR-017) |
| `auth_config` | JSONB | NOT NULL, default `{}` | Auth type + credential ref; never stores raw secrets |
| `status` | mcp_server_status | NOT NULL, default `active` | active / suspended / deregistered |
| `catalog_ttl_seconds` | INTEGER | NOT NULL, default 3600 | Per-server TTL override |
| `last_catalog_fetched_at` | TIMESTAMPTZ | NULLABLE | Timestamp of last successful fetch |
| `catalog_version_snapshot` | VARCHAR(128) | NULLABLE | Version string from last catalog fetch |
| `created_by` | UUID | FK → users, NOT NULL | Operator who registered the server |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes**: `(workspace_id)`, `(workspace_id, endpoint_url)` UNIQUE (FR-024)

---

### `mcp_exposed_tools`

Platform tools designated by operators as discoverable and invokable by external MCP clients.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `workspace_id` | UUID | FK → workspaces, NULLABLE | NULL = platform-wide exposure |
| `tool_fqn` | VARCHAR(512) | NOT NULL | Native platform tool identifier |
| `mcp_tool_name` | VARCHAR(128) | NOT NULL | Name as exposed to external MCP clients |
| `mcp_description` | TEXT | NOT NULL | MCP-compliant tool description |
| `mcp_input_schema` | JSONB | NOT NULL | JSON Schema for tool input parameters |
| `is_exposed` | BOOLEAN | NOT NULL, default FALSE | Runtime toggle (FR-019 / SC-013) |
| `created_by` | UUID | FK → users, NOT NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes**: `(tool_fqn, workspace_id)` UNIQUE, `(is_exposed)` partial where TRUE

---

### `mcp_catalog_cache`

Durable fallback for external MCP server tool catalogs (Redis is the hot tier).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `server_id` | UUID | FK → mcp_server_registrations, UNIQUE NOT NULL | One row per server |
| `tools_catalog` | JSONB | NOT NULL | Array of tool definitions fetched from external server |
| `resources_catalog` | JSONB | NULLABLE | Array of resource definitions |
| `prompts_catalog` | JSONB | NULLABLE | Array of prompt templates |
| `fetched_at` | TIMESTAMPTZ | NOT NULL | Timestamp of the successful fetch |
| `version_snapshot` | VARCHAR(128) | NULLABLE | MCP version string from capabilities |
| `is_stale` | BOOLEAN | NOT NULL, default FALSE | Set when refresh fetch fails (FR-016) |
| `next_refresh_at` | TIMESTAMPTZ | NOT NULL | Scheduled next refresh time |

**Indexes**: `(server_id)` UNIQUE, `(next_refresh_at)` for scheduler queries

---

### `mcp_invocation_audit_records`

Immutable audit trail for every MCP tool invocation (inbound and outbound).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `workspace_id` | UUID | NULLABLE | Resolved from principal or agent |
| `principal_id` | UUID | NULLABLE | Inbound: external client principal; outbound: executing agent |
| `agent_id` | UUID | FK → registry_agent_profiles, NULLABLE | Outbound only |
| `agent_fqn` | VARCHAR(512) | NULLABLE | Outbound only |
| `server_id` | UUID | FK → mcp_server_registrations, NULLABLE | Outbound only |
| `tool_identifier` | VARCHAR(512) | NOT NULL | Namespaced for outbound; native fqn for inbound |
| `direction` | mcp_invocation_direction | NOT NULL | inbound / outbound |
| `outcome` | mcp_invocation_outcome | NOT NULL | allowed / denied / error_transient / error_permanent |
| `policy_decision` | JSONB | NULLABLE | Gate result from tool gateway |
| `payload_size_bytes` | INTEGER | NULLABLE | Actual payload size for size-limit violations |
| `error_code` | VARCHAR(64) | NULLABLE | MCP or platform error code |
| `error_classification` | VARCHAR(32) | NULLABLE | "transient" or "permanent" (FR-013 / SC-010) |
| `timestamp` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes**: `(workspace_id, timestamp DESC)`, `(agent_id, timestamp DESC)`, `(server_id, timestamp DESC)`, `(outcome)` partial where outcome != 'allowed'

---

## Modified Table

### `registry_agent_profiles` — new column

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `mcp_server_refs` | JSONB | NOT NULL, default `'[]'` | List of MCPServerRegistration UUIDs (string form) |

**Rationale**: Additive nullable-with-default column (Brownfield Rule 7). Follows the existing JSONB list pattern (`role_types`, `visibility_agents`, `visibility_tools`, `tags`).

**Index**: GIN index on `mcp_server_refs` for queries like "all agents using server X".

---

## Enums

### `mcp_server_status`

```sql
CREATE TYPE mcp_server_status AS ENUM ('active', 'suspended', 'deregistered');
```

### `mcp_invocation_direction`

```sql
CREATE TYPE mcp_invocation_direction AS ENUM ('inbound', 'outbound');
```

### `mcp_invocation_outcome`

```sql
CREATE TYPE mcp_invocation_outcome AS ENUM (
    'allowed',
    'denied',
    'error_transient',
    'error_permanent'
);
```

---

## Redis Keys

| Key Pattern | Type | TTL | Purpose |
|-------------|------|-----|---------|
| `cache:mcp_catalog:{server_id}` | STRING (JSON) | `MCP_CATALOG_TTL_SECONDS` (default 3600s) | Hot catalog cache; fallback to `mcp_catalog_cache` DB row |
| `cache:mcp_server_health:{server_id}` | HASH | 90s | Health aggregate: `{status, last_success_at, error_count_5m, last_error_at}` |

---

## Kafka Topic

**Topic**: `mcp.events`

| Event Type | Producer | Payload Key Fields |
|------------|----------|--------------------|
| `mcp.server.registered` | `MCPService` | `server_id`, `workspace_id`, `endpoint_url` |
| `mcp.server.suspended` | `MCPService` | `server_id`, `workspace_id`, `reason` |
| `mcp.server.deregistered` | `MCPService` | `server_id`, `workspace_id` |
| `mcp.catalog.refreshed` | `MCPToolRegistry` | `server_id`, `tool_count`, `version_snapshot` |
| `mcp.catalog.stale` | `MCPToolRegistry` | `server_id`, `cached_at`, `error_summary` |
| `mcp.tool.invoked` | `MCPServerService` / `MCPToolRegistry` | `direction`, `server_id`, `tool_identifier`, `agent_id`, `outcome` |
| `mcp.tool.denied` | `MCPServerService` / `ToolGatewayService` | `direction`, `tool_identifier`, `block_reason`, `workspace_id` |

---

## Schema Changes — Pydantic (registry/schemas.py)

### `AgentManifest` (new optional field)

```python
mcp_servers: list[str] = []   # UUIDs of MCPServerRegistration records
```

### `AgentProfileResponse` (new optional field)

```python
mcp_servers: list[str] = []
```

### `AgentPatch` (new optional field)

```python
mcp_servers: list[str] | None = None   # None = no change; [] = clear all
```

---

## Alembic Migration

**File**: `apps/control-plane/migrations/versions/053_mcp_integration.py`

```python
revision = "053_mcp_integration"
down_revision = "052_a2a_gateway"
```

**Up operations** (in order):
1. `CREATE TYPE mcp_server_status AS ENUM (…)`
2. `CREATE TYPE mcp_invocation_direction AS ENUM (…)`
3. `CREATE TYPE mcp_invocation_outcome AS ENUM (…)`
4. `CREATE TABLE mcp_server_registrations (…)`
5. `CREATE TABLE mcp_exposed_tools (…)`
6. `CREATE TABLE mcp_catalog_cache (…)`
7. `CREATE TABLE mcp_invocation_audit_records (…)`
8. `ALTER TABLE registry_agent_profiles ADD COLUMN mcp_server_refs JSONB NOT NULL DEFAULT '[]'`
9. `CREATE INDEX ix_registry_agent_profiles_mcp_server_refs ON registry_agent_profiles USING GIN (mcp_server_refs)`
