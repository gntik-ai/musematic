# Mock OAuth Servers Contract

**Feature**: 072-user-journey-e2e-tests
**Date**: 2026-04-21
**Deployments**: `mock-google-oidc` + `mock-github-oauth` under namespace `platform`

Both servers are minimal in-cluster stubs exposing the exact endpoints required by the platform's OAuth adapters for journey-driven login flows. They run ONLY when `FEATURE_E2E_MODE=true` (inherits feature 071's gate — no second flag).

---

## Helm overlay additions (`tests/e2e/cluster/values-e2e.yaml`)

```yaml
mockOAuth:
  google:
    enabled: true                              # gated by FEATURE_E2E_MODE at chart level
    image: ghcr.io/musematic/mock-google-oidc:local
    replicas: 1
    service:
      type: ClusterIP
      port: 8080
    resources:
      requests: { memory: 64Mi, cpu: 50m }
      limits:   { memory: 128Mi, cpu: 200m }
    seedUsers:                                 # in-memory on pod start
      - key: j-admin
        sub: google-admin-001
        email: j-admin@company.com
        email_verified: true
      - key: j-creator
        sub: google-creator-001
        email: j-creator@company.com
        email_verified: true
      - key: j-consumer
        sub: google-consumer-001
        email: j-consumer@company.com
        email_verified: true

  github:
    enabled: true
    image: ghcr.io/musematic/mock-github-oauth:local
    replicas: 1
    service:
      type: ClusterIP
      port: 8080
    resources:
      requests: { memory: 64Mi, cpu: 50m }
      limits:   { memory: 128Mi, cpu: 200m }
    seedUsers:
      - key: j-admin-gh
        id: 1001
        login: j-admin
        email: j-admin@company.com
      - key: j-creator-gh
        id: 1002
        login: j-creator
        email: j-creator@company.com
```

**Production safety**: the chart template sets both `mockOAuth.google.enabled` and `mockOAuth.github.enabled` to `false` unless `features.e2eMode` is true. In-cluster DNS names (`mock-google-oidc.platform.svc.cluster.local:8080` / `mock-github-oauth.platform.svc.cluster.local:8080`) are only resolvable from inside the cluster; they are never exposed via ingress.

---

## Mock Google OIDC — Endpoint Contract

Base URL in-cluster: `http://mock-google-oidc:8080`
Base URL from platform perspective: configured via `OAUTH_GOOGLE_AUTHORIZE_URL`, `OAUTH_GOOGLE_TOKEN_URL`, `OAUTH_GOOGLE_USERINFO_URL`, `OAUTH_GOOGLE_JWKS_URL` env vars set by the values overlay.

### `GET /authorize`

**Query params**: `client_id`, `redirect_uri`, `response_type=code`, `scope`, `state`, `nonce`, `login_hint` (optional, used by mock to pick seed user — mapped to `key`)

**Response**: HTTP 302 redirect to `redirect_uri?code={code}&state={state}` where `code` is a per-call UUID keyed to `(login_hint, state)` in the mock's in-memory TTL-keyed state (TTL: 5 min).

If `login_hint` unknown: HTTP 400 with JSON body `{"error": "invalid_login_hint"}`.

### `POST /token`

**Request body** (form-encoded): `grant_type=authorization_code`, `code`, `redirect_uri`, `client_id`, `client_secret`

**Response 200**:
```json
{
  "access_token": "mock-oidc-access-{random}",
  "id_token": "<RS256 JWT signed with mock's private key>",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "openid email profile"
}
```

The `id_token` JWT contains: `iss=http://mock-google-oidc:8080`, `aud={client_id}`, `sub=seed.sub`, `email=seed.email`, `email_verified=seed.email_verified`, `iat`, `exp`, `nonce` (from authorize call).

**Response 400** if `code` is unknown, expired, or already used: `{"error": "invalid_grant"}`.

### `GET /userinfo`

**Auth**: Bearer access_token (from `/token`)

**Response 200**:
```json
{
  "sub": "google-admin-001",
  "email": "j-admin@company.com",
  "email_verified": true,
  "name": "J Admin",
  "picture": "http://mock-google-oidc:8080/avatars/google-admin-001.png"
}
```

### `GET /.well-known/jwks.json`

Returns the mock server's public RSA key set in JWKS format. Platform's OIDC adapter uses this to verify the `id_token` signature.

### `GET /.well-known/openid-configuration`

Returns standard OIDC discovery document pointing to the endpoints above.

---

## Mock GitHub OAuth — Endpoint Contract

Base URL in-cluster: `http://mock-github-oauth:8080`

### `GET /login/oauth/authorize`

**Query params**: `client_id`, `redirect_uri`, `scope`, `state`, `login` (mock-specific — mapped to `key`)

**Response**: HTTP 302 redirect to `redirect_uri?code={code}&state={state}`.

### `POST /login/oauth/access_token`

**Request body** (form-encoded): `client_id`, `client_secret`, `code`, `redirect_uri`

**Response 200** (default content-type `application/x-www-form-urlencoded`, JSON if `Accept: application/json`):
```json
{
  "access_token": "gho_mock_{random}",
  "token_type": "bearer",
  "scope": "read:user user:email"
}
```

### `GET /user`

**Auth**: `Authorization: Bearer <access_token>` OR `Authorization: token <access_token>`

**Response 200**:
```json
{
  "id": 1001,
  "login": "j-admin",
  "email": "j-admin@company.com",
  "name": "J Admin",
  "avatar_url": "http://mock-github-oauth:8080/avatars/1001.png"
}
```

### `GET /user/emails`

**Response 200**:
```json
[{"email": "j-admin@company.com", "primary": true, "verified": true, "visibility": "public"}]
```

---

## State management

Both mocks maintain an in-memory dict keyed by `(state, code)` with a 5-minute TTL. Parallel journeys never collide because each journey generates a fresh UUID `state` per authorize call.

**Restart behavior**: pod restart clears all state. Seed users are rebuilt from the ConfigMap on startup. No persistent volumes.

**Observability**: both mocks emit access logs to stdout; pod logs are captured by feature 071's `capture-state.sh` on failure.

---

## Platform-side configuration (via `values-e2e.yaml`)

```yaml
auth:
  oauth:
    google:
      authorize_url: "http://mock-google-oidc:8080/authorize"
      token_url: "http://mock-google-oidc:8080/token"
      userinfo_url: "http://mock-google-oidc:8080/userinfo"
      jwks_url: "http://mock-google-oidc:8080/.well-known/jwks.json"
      issuer: "http://mock-google-oidc:8080"
      client_id: "mock-google-client-id"
      client_secret: "mock-google-client-secret"
    github:
      authorize_url: "http://mock-github-oauth:8080/login/oauth/authorize"
      token_url: "http://mock-github-oauth:8080/login/oauth/access_token"
      user_url: "http://mock-github-oauth:8080/user"
      emails_url: "http://mock-github-oauth:8080/user/emails"
      client_id: "mock-github-client-id"
      client_secret: "mock-github-client-secret"
```

These env vars are injected into control-plane pods only when `features.e2eMode: true`. In production, the real Google/GitHub OAuth URLs are used (or OAuth is disabled entirely).

---

## Journey usage

Journey tests reference the mock server URLs via pytest fixtures:

```python
@pytest.fixture(scope="session")
def mock_google_oidc() -> str:
    return "http://mock-google-oidc:8080"

@pytest.fixture(scope="session")
def mock_github_oauth() -> str:
    return "http://mock-github-oauth:8080"
```

These URLs are passed to `oauth_login(client, provider="google", mock_server=mock_google_oidc, login="j-admin")`, which drives the complete OAuth flow end-to-end.

---

## Production safety assertion (inherits feature 071)

`tests/e2e/test_chart_identity.py` (from feature 071) continues to pass: no new `Chart.yaml` introduced. The mock OAuth overlays are purely additions to `values-e2e.yaml` — same chart, different values.

`apps/control-plane/tests/unit/testing/test_router_e2e_404_when_flag_off.py` remains unaffected because no new `/api/v1/_e2e/*` endpoints are added by this feature.

A new unit test `test_mock_oauth_disabled_in_production.py` verifies: with `features.e2eMode=false`, `helm template deploy/helm/platform/` produces zero Deployments named `mock-google-oidc` or `mock-github-oauth` — enforced at every CI run via the existing chart-identity check pattern.
