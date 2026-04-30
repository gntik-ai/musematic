# Self-Service Surfaces

UPD-042 adds user-facing counterparts for backend and admin-side capabilities required by FR-649 through FR-657. These pages reduce support load while preserving the admin workbench as the control plane for oversight, escalation, and policy enforcement.

| User Surface | Admin or Backend Equivalent | Admin Notes |
| --- | --- | --- |
| `/notifications` | Persistent `UserAlert` rows and notification delivery ledger | Users can review and mark their own alerts read. Admins troubleshoot delivery providers and workspace-wide incidents. |
| `/settings/notifications` | Notification channel and deliverer configuration | Users can choose event-channel preferences, digest mode, and quiet hours. Mandatory `security.*` and `incidents.*` events must retain at least one channel. |
| `/settings/api-keys` | Admin service-account credential controls | Users can create up to 10 personal API keys scoped to their own permissions. Admin-created service accounts remain separate. |
| `/settings/security/mfa` | Admin MFA reset and policy controls | Users can enroll, regenerate backup codes, and disable MFA only when policy permits it. |
| `/settings/security/sessions` | Auth session store | Users can revoke specific sessions or all other sessions. The current session must be refused by the API. |
| `/settings/security/activity` | Audit chain | Users see entries where they are actor or subject. Admin audit search remains broader. |
| `/settings/privacy/consent` | Privacy consent records | Users can revoke their own consent. Admin on-behalf actions must preserve Rule 34 double-audit behavior. |
| `/settings/privacy/dsr` | Admin DSR queue | Self-service submissions use the same DSR service and appear in the admin queue with `source=self_service`. |

## Admin-On-Behalf Actions

When an administrator acts on behalf of a user, the system must make the authority boundary explicit:

- The acting admin is the audit actor.
- The affected user is the audit subject.
- Rule 34 double-audit applies to impersonation and on-behalf privacy actions.
- Admin actions must never be represented as self-service actions.

## Support Guidance

Use self-service pages first when the user can safely complete the action. Escalate to admin tools only when policy, lost credentials, legal review, or incident response requires an operator.

Do not ask users to send API keys, TOTP secrets, backup codes, or raw session tokens. Rule 31 secret handling still applies to support workflows.
