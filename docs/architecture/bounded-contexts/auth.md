# Auth

Auth owns login, token issuance, token refresh, MFA enrollment, sessions, lockout, RBAC interpretation, and service account keys.

Primary entities include credentials, sessions, MFA secrets, recovery codes, roles, and service accounts. The REST surface includes login, refresh, logout, MFA, OAuth-adjacent auth operations, and session invalidation. Events are emitted on `auth.events` for login, logout, MFA, credential, and session lifecycle changes.

Auth works closely with Accounts for user state and with Audit for security evidence.
