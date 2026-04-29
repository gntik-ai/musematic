# Admin Action Impact Tiers

| Action | Route / API | Tier | Confirmation |
|---|---|---|---|
| View users | `/admin/users`, `GET /api/v1/admin/users` | no-confirmation | None |
| Create user | `/admin/users` | simple | Confirm create |
| Suspend one user | `POST /api/v1/admin/users/{id}/suspend` | typed | Type affected user name |
| Bulk suspend users | `POST /api/v1/admin/users/bulk/suspend` | typed | Type `SUSPEND {count} USERS` |
| Delete user | `DELETE /api/v1/admin/users/{id}` | 2pa | 2PA when deleting privileged users |
| Force MFA enrollment | `POST /api/v1/admin/users/{id}/force-mfa-enrollment` | simple | Confirm action |
| Force password reset | `POST /api/v1/admin/users/{id}/force-password-reset` | simple | Confirm action |
| Revoke session | `DELETE /api/v1/admin/sessions/{id}` | simple | Confirm revoke |
| Create OAuth provider | `POST /api/v1/admin/oauth-providers` | typed | Type provider key |
| Rotate connector secret | `/api/v1/admin/connectors/{id}/rotate-secret` | typed | Type `ROTATE SECRET` |
| Update feature flag | `PUT /api/v1/admin/feature-flags/{key}` | simple | Confirm setting |
| Switch tenant mode | `/api/v1/admin/tenant-mode` | 2pa | 2PA required |
| Execute failover | `POST /api/v1/admin/regions/failover/execute` | 2pa | 2PA required; approver differs from initiator |
| Schedule maintenance | `POST /api/v1/admin/maintenance` | simple | Confirm window |
| Export configuration | `POST /api/v1/admin/config/export` | simple | Confirm export |
| Import configuration preview | `POST /api/v1/admin/config/import/preview` | no-confirmation | None |
| Import configuration apply | `POST /api/v1/admin/config/import/apply` | typed | Type `IMPORT CONFIG` |
| Start impersonation | `POST /api/v1/admin/impersonation/start` | typed | Justification >= 20 chars |
| Impersonate super admin | `POST /api/v1/admin/impersonation/start` | 2pa | 2PA token required |
| End impersonation | `POST /api/v1/admin/impersonation/end` | simple | Confirm end |
| Enable read-only mode | `PATCH /api/v1/admin/sessions/me/read-only-mode` | simple | Toggle |
| Disable read-only mode | `PATCH /api/v1/admin/sessions/me/read-only-mode` | 2pa | MFA step-up required |
| Break-glass recovery | `platform-cli superadmin recover` | 2pa | Emergency key + critical audit |
| Force reset super admin | `platform-cli superadmin reset --force` | 2pa | Production requires `ALLOW_SUPERADMIN_RESET=true` |

The UI chooses the weakest tier that still satisfies the row above. Server-side enforcement remains authoritative for 2PA, tenant mode, impersonation, and read-only mode.
