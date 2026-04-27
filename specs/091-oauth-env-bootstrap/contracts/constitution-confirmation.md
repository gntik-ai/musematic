# Constitution Confirmation — UPD-041 OAuth Env Bootstrap

Date: 2026-04-27

Confirmed anchors in `.specify/memory/constitution.md`:

- Rule 10: every credential goes through vault.
- Rule 30: every admin endpoint declares a role gate.
- Rule 31: super-admin bootstrap never logs secrets.
- Rule 39: every secret resolves via `SecretProvider`; direct secret-pattern env reads are denied outside provider implementations.
- Rule 42: OAuth env-var bootstrap is idempotent.
- Rule 43: OAuth client secrets live in Vault, never in the database.
- Rule 44: rotation responses never return the new secret.

Implementation implication: UPD-041 stores only `client_secret_ref` paths in PostgreSQL, writes secret values through the `SecretProvider` Protocol, keeps rotate-secret responses as 204 No Content, and adds `_require_platform_admin(current_user)` gates on the new admin endpoints.
