# OpenAPI Publication + Developer Documentation Endpoints

**Feature**: 073-api-governance-dx
**Date**: 2026-04-23

This contract covers how the platform exposes its OpenAPI 3.1 document
and the interactive Swagger UI / Redoc renderings.

---

## Endpoints

### `GET /api/openapi.json`

Returns the canonical OpenAPI 3.1 document.

| Aspect | Specification |
|---|---|
| **Auth** | None (anonymous-tier rate limited) |
| **Content-Type** | `application/json` |
| **Content-Encoding** | `gzip` when the client sends `Accept-Encoding: gzip` |
| **Body** | FastAPI-generated `app.openapi()` output |
| **Caching** | `Cache-Control: public, max-age=60` — doc is effectively immutable within a release |
| **Response headers** | `X-RateLimit-*` (anonymous-tier) and `ETag` |

**OpenAPI document requirements** (enforced in CI):

- Valid OpenAPI 3.1.
- `info.title = "musematic Control Plane API"`.
- `info.version` equals the platform release version (e.g. `1.4.0`).
- `info.contact` present with platform-level email.
- Every path is tagged with its owning bounded-context name (enforced
  by a CI check that walks the generated doc and fails if any path
  has no tag).
- Admin-only paths (prefix `/api/v1/admin/`) carry the `admin` tag in
  addition to their bounded-context tag (per constitution rule 29 and
  research.md D-002).
- `securitySchemes` declares `session` (cookie), `oauth2` (Google /
  GitHub), and `apiKey` (header `Authorization: Bearer msk_…`).
- Every non-public operation declares a non-empty `security` array.
- Deprecated operations carry `deprecated: true` with the sunset date
  in the `description`.
- Passes `spectral lint` or `redocly lint` with zero errors and no
  high-severity warnings.

### `GET /api/docs`

Serves Swagger UI sourced from `/api/openapi.json`.

| Aspect | Specification |
|---|---|
| **Auth** | None |
| **Content-Type** | `text/html` |
| **Body** | FastAPI's default Swagger UI template with `openapi_url="/api/openapi.json"` |
| **Response headers** | `Content-Security-Policy` standard for Swagger UI assets |

### `GET /api/redoc`

Serves Redoc sourced from `/api/openapi.json`.

| Aspect | Specification |
|---|---|
| **Auth** | None |
| **Content-Type** | `text/html` |
| **Body** | FastAPI's default Redoc template with `openapi_url="/api/openapi.json"` |

---

## FastAPI constructor changes

In `apps/control-plane/src/platform/main.py:712` (`create_app`):

```python
app = FastAPI(
    lifespan=_lifespan,
    title="musematic Control Plane API",
    version=resolved.platform_release_version,
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    contact={
        "name": "musematic platform",
        "email": "platform@musematic.ai",
    },
)
```

---

## Auth-middleware EXEMPT_PATHS update

`apps/control-plane/src/platform/common/auth_middleware.py:11-24` —
replace the current block with:

```python
EXEMPT_PATHS: frozenset[str] = frozenset({
    "/health",
    "/healthz",
    "/api/v1/healthz",
    "/api/openapi.json",
    "/api/docs",
    "/api/redoc",
    # legacy paths retained for one release cycle — removed in 1.5.0
    "/openapi.json",
    "/docs",
    "/redoc",
    # existing auth / account endpoints preserved …
})
```

---

## CI gate: OpenAPI lint

New job in `.github/workflows/ci.yml` (added after Python tests):

```yaml
openapi-lint:
  name: OpenAPI lint
  runs-on: ubuntu-latest
  needs: [tests-python]
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.12"
    - name: Install deps
      run: |
        cd apps/control-plane
        pip install -e ".[dev]"
    - name: Generate OpenAPI doc
      run: |
        cd apps/control-plane
        python -c "from platform.main import create_app; import json; print(json.dumps(create_app().openapi()))" > /tmp/openapi.json
    - name: Lint with Spectral
      uses: stoplightio/spectral-action@v0.8.1
      with:
        file_glob: /tmp/openapi.json
        spectral_ruleset: '.spectral.yaml'
```

A `.spectral.yaml` ruleset at repo root extends `spectral:oas` and adds
custom rules for:

- Every operation MUST have at least one tag.
- Every non-anonymous operation MUST have a non-empty `security` array.
- Operations under `/api/v1/admin/` MUST carry the `admin` tag.
- Deprecated operations MUST set a `sunset` date in their description.

---

## SDK-generation input

The SDK workflow (`sdks.yml`) fetches
`https://api.musematic.ai/api/openapi.json` from the newly-tagged
release deployment. It filters operations tagged `admin` before
generating client code (per D-002). Each generator supports tag-level
filtering out of the box.
