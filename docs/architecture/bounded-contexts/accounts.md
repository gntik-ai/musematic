# Accounts

Accounts owns user registration, email verification, invitations, signup modes, admin approval, and lifecycle actions such as suspend, block, archive, and reactivate.

Primary entities include users, invitations, approval requests, verification tokens, and lifecycle state. The REST surface is rooted at `/api/v1/accounts`. Events are emitted on `accounts.events` and are consumed by workspaces, audit, notifications, and dashboards.

Accounts enforces anti-enumeration behavior for public signup and coordinates with Auth for credential and session changes.
