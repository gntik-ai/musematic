# REST Contract: Health Endpoint

**Path**: `GET /health`  
**Auth**: Exempt (no JWT required)  
**Feature**: 013-fastapi-app-scaffold

---

## Response (200 OK)

```json
{
  "status": "healthy" | "degraded" | "unhealthy",
  "uptime_seconds": 3600,
  "profile": "api",
  "dependencies": {
    "postgresql": { "status": "healthy", "latency_ms": 2 },
    "redis": { "status": "healthy", "latency_ms": 1 },
    "kafka": { "status": "healthy", "latency_ms": 5 },
    "qdrant": { "status": "healthy", "latency_ms": 3 },
    "neo4j": { "status": "healthy", "latency_ms": 4 },
    "clickhouse": { "status": "healthy", "latency_ms": 6 },
    "opensearch": { "status": "healthy", "latency_ms": 7 },
    "minio": { "status": "healthy", "latency_ms": 2 },
    "runtime_controller": { "status": "healthy", "latency_ms": 1 },
    "reasoning_engine": { "status": "healthy", "latency_ms": 1 },
    "sandbox_manager": { "status": "healthy", "latency_ms": 1 },
    "simulation_controller": { "status": "healthy", "latency_ms": 1 }
  }
}
```

## Status Logic

- **healthy**: All dependencies report healthy
- **degraded**: At least one dependency is unhealthy but the application is running
- **unhealthy**: Critical dependencies (PostgreSQL) are down

## Error Body Format (all routes)

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Resource not found",
    "details": {}
  }
}
```

## Correlation Headers

| Header | Direction | Description |
|--------|-----------|-------------|
| `X-Correlation-ID` | Request/Response | Propagated or auto-generated UUID |
| `X-Request-ID` | Response | Server-generated request ID |

## Auth Exempt Paths

- `GET /health`
- `GET /docs`
- `GET /openapi.json`
- `GET /redoc`
