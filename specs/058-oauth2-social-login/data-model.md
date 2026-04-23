# Data Model: OAuth2 Social Login (Google and GitHub)

**Phase 1 output for**: [plan.md](plan.md)  
**Date**: 2026-04-18

## New Database Tables

### `oauth_providers`

Admin-managed record for each external identity provider.

```sql
CREATE TABLE oauth_providers (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_type  VARCHAR(32)  NOT NULL,
    display_name   VARCHAR(128) NOT NULL,
    enabled        BOOLEAN      NOT NULL DEFAULT false,
    client_id      VARCHAR(256) NOT NULL,
    client_secret_ref VARCHAR(256) NOT NULL,
    redirect_uri   VARCHAR(512) NOT NULL,
    scopes         JSONB        NOT NULL DEFAULT '[]',
    domain_restrictions JSONB   DEFAULT '[]',
    org_restrictions    JSONB   DEFAULT '[]',
    group_role_mapping  JSONB   DEFAULT '{}',
    default_role   VARCHAR(64)  NOT NULL DEFAULT 'member',
    require_mfa    BOOLEAN      NOT NULL DEFAULT false,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_oauth_providers_type UNIQUE (provider_type)
);
```

**Notes**:
- `provider_type` values in scope: `'google'`, `'github'`. UNIQUE constraint enforces one row per provider.
- `client_secret_ref` is a reference string (e.g., `k8s:platform-control/oauth-google/client-secret`) — never a secret value.
- `scopes` is a JSONB array of OAuth scope strings (e.g., `["openid", "email", "profile"]`).
- `domain_restrictions` / `org_restrictions`: JSONB string arrays; empty = no restriction.
- `group_role_mapping`: JSONB object `{"<group_name>": "<role_type>"}`.
- `require_mfa`: when `true`, platform MFA challenge issued post-provider-sign-in before session is issued.

---

### `oauth_links`

Association between a platform user and their identity at one provider.

```sql
CREATE TABLE oauth_links (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_id       UUID         NOT NULL REFERENCES oauth_providers(id),
    external_id       VARCHAR(256) NOT NULL,
    external_email    VARCHAR(256),
    external_name     VARCHAR(256),
    external_avatar_url VARCHAR(512),
    external_groups   JSONB        DEFAULT '[]',
    linked_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_login_at     TIMESTAMPTZ,
    CONSTRAINT uq_oauth_links_provider_ext  UNIQUE (provider_id, external_id),
    CONSTRAINT uq_oauth_links_user_provider UNIQUE (user_id, provider_id)
);
CREATE INDEX idx_oauth_links_user ON oauth_links(user_id);
```

**Notes**:
- `external_id` = Google `sub` claim or GitHub numeric user ID (stored as string).
- `external_groups` updated on every successful sign-in (FR-028).
- `UNIQUE(user_id, provider_id)` enforces one link per user per provider.
- `UNIQUE(provider_id, external_id)` enforces one platform user per external identity.
- `ON DELETE CASCADE` on `user_id`: when a user is deleted, their OAuth links are removed.

---

### `oauth_audit_entries`

Immutable append-only audit log for all OAuth events.

```sql
CREATE TABLE oauth_audit_entries (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_type   VARCHAR(32),
    provider_id     UUID         REFERENCES oauth_providers(id),
    user_id         UUID         REFERENCES users(id),
    external_id     VARCHAR(256),
    action          VARCHAR(64)  NOT NULL,
    outcome         VARCHAR(32)  NOT NULL,
    failure_reason  VARCHAR(256),
    source_ip       VARCHAR(64),
    user_agent      TEXT,
    actor_id        UUID,
    changed_fields  JSONB,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_oauth_audit_user     ON oauth_audit_entries(user_id, created_at DESC);
CREATE INDEX idx_oauth_audit_provider ON oauth_audit_entries(provider_id, created_at DESC);
```

**`action` values**: `sign_in`, `sign_in_failed`, `account_linked`, `account_unlinked`, `user_provisioned`, `provider_configured`  
**`outcome` values**: `success`, `failure`  
**`actor_id`**: set for admin actions (provider configuration changes); NULL for user-initiated events  
**`changed_fields`**: JSONB for config changes, with secret refs masked; NULL for sign-in events

---

## SQLAlchemy Models

**File**: `apps/control-plane/src/platform/auth/models.py` — **APPEND** after existing content

```python
# ── OAuth2 Social Login ────────────────────────────────────────────────────────

class OAuthProvider(Base, UUIDMixin, TimestampMixin):
    """Admin-managed configuration for one external identity provider."""
    __tablename__ = "oauth_providers"

    provider_type: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    client_id: Mapped[str] = mapped_column(String(256), nullable=False)
    client_secret_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(512), nullable=False)
    scopes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    domain_restrictions: Mapped[list] = mapped_column(JSONB, default=list)
    org_restrictions: Mapped[list] = mapped_column(JSONB, default=list)
    group_role_mapping: Mapped[dict] = mapped_column(JSONB, default=dict)
    default_role: Mapped[str] = mapped_column(String(64), nullable=False, default="member")
    require_mfa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    links: Mapped[list["OAuthLink"]] = relationship(
        "OAuthLink", back_populates="provider", lazy="selectin"
    )


class OAuthLink(Base, UUIDMixin):
    """Association between a platform user and one external identity."""
    __tablename__ = "oauth_links"
    __table_args__ = (
        UniqueConstraint("provider_id", "external_id"),
        UniqueConstraint("user_id", "provider_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("oauth_providers.id"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(256), nullable=False)
    external_email: Mapped[str | None] = mapped_column(String(256))
    external_name: Mapped[str | None] = mapped_column(String(256))
    external_avatar_url: Mapped[str | None] = mapped_column(String(512))
    external_groups: Mapped[list] = mapped_column(JSONB, default=list)
    linked_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ(timezone=True), nullable=False, server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ(timezone=True))

    provider: Mapped["OAuthProvider"] = relationship("OAuthProvider", back_populates="links")


class OAuthAuditEntry(Base, UUIDMixin):
    """Immutable record of every OAuth event — sign-in, link, unlink, config change."""
    __tablename__ = "oauth_audit_entries"

    provider_type: Mapped[str | None] = mapped_column(String(32))
    provider_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("oauth_providers.id")
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id")
    )
    external_id: Mapped[str | None] = mapped_column(String(256))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(256))
    source_ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    changed_fields: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ(timezone=True), nullable=False, server_default=func.now()
    )
```

---

## New Source Files

| File | Purpose |
|---|---|
| `auth/services/oauth_providers/__init__.py` | Package marker |
| `auth/services/oauth_providers/google.py` | `GoogleOAuthProvider` — auth URL, token exchange, JWKS ID token validation, domain check, group fetch |
| `auth/services/oauth_providers/github.py` | `GitHubOAuthProvider` — auth URL, token exchange, user/email/org/team API calls |
| `auth/services/oauth_service.py` | `OAuthService` — PKCE + state management, callback orchestration, find-or-create user, link/unlink |
| `auth/repository_oauth.py` | `OAuthRepository` — all DB queries for oauth tables |
| `auth/router_oauth.py` | FastAPI router — 7 endpoints, rate-limit dependency on callback |
| `auth/dependencies_oauth.py` | `build_oauth_service()` factory + `rate_limit_callback` dependency |
| `migrations/versions/045_oauth_providers_and_links.py` | Alembic migration — creates 3 tables |

---

## Modified Files

| File | Lines | Change |
|---|---|---|
| `auth/models.py` | append after last model | Add `OAuthProvider`, `OAuthLink`, `OAuthAuditEntry` classes |
| `auth/schemas.py` | append after last schema | Add `OAuthProviderCreate`, `OAuthProviderUpdate`, `OAuthProviderPublic`, `OAuthProviderAdminResponse`, `OAuthLinkResponse`, `OAuthAuthorizeResponse`, `OAuthCallbackResult`, `OAuthAuditEntryResponse` |
| `auth/events.py` | append after existing event types | Add 6 new OAuth event type strings + payload models |
| `common/config.py` | `AuthSettings` class | Add `oauth_state_secret`, `oauth_state_ttl`, `oauth_jwks_cache_ttl`, `oauth_rate_limit_max`, `oauth_rate_limit_window` fields |
| `main.py` | line ~748 (after `app.include_router(auth_router)`) | Add `from platform.auth.router_oauth import oauth_router` + `app.include_router(oauth_router)` |

---

## Redis Keys (New)

| Key Pattern | Value | TTL | Notes |
|---|---|---|---|
| `oauth:state:{nonce}` | JSON `{code_verifier, provider_type, created_at}` | 600 s | Single-use; deleted on first successful validation |
| `cache:google-jwks:certs` | Raw Google JWKS JSON string | 3600 s | Refreshed on cache miss or unknown key ID |
| `ratelimit:oauth-callback:{ip}` | Integer counter | `oauth_rate_limit_window` s | Per-IP callback rate limit |

---

## Entities and State Transitions

### OAuthProvider — Enabled State Machine

```
created (enabled=false) ──[admin enables]──→ enabled
enabled ──[admin disables]──→ disabled
disabled ──[admin enables]──→ enabled
```

When disabled: callbacks for that provider fail before any state lookup.

### Sign-In Flow State

```
/authorize called
  → state entry written to Redis (oauth:state:{nonce})
  → PKCE verifier embedded in state value
  → redirect to provider

/callback called
  → rate check (ratelimit:oauth-callback:{ip})
  → state lookup in Redis → delete state entry (single-use)
  → HMAC integrity check
  → token exchange with provider
  → ID token validation (Google) / user API call (GitHub)
  → domain / org restriction check
  → find-or-create user
  → write oauth_audit_entries
  → publish to auth.events Kafka
  → create_session() via AuthService
  → return session token
```
