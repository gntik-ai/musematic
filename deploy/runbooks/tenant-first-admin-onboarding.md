# Tenant First-Admin Onboarding Runbook

## Scope

This runbook covers UPD-048 public signup at the default tenant, Enterprise first-admin `/setup`, missing default workspace recovery, and cross-tenant identity acceptance.

## Provision The First Enterprise Tenant

1. Provision the tenant from the superadmin tenant inventory.
2. Confirm the tenant row is active and DNS records are ready.
3. Confirm a `tenant_first_admin_invitations` row exists for the first admin email.
4. Ask the admin to open the `/setup?token=...` link on the Enterprise tenant subdomain.

The setup flow requires TOS acceptance, credentials, MFA verification with recovery-code acknowledgement, first workspace creation, optional invitations, and setup completion.

## Resend A First-Admin Invitation

Use:

```bash
curl -X POST \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  "$PLATFORM_API_URL/api/v1/admin/tenants/$TENANT_ID/resend-first-admin-invitation"
```

Resend invalidates the prior token immediately. A previously sent link must return `410 setup_token_invalid`.

## Troubleshoot MFA Enrollment

- If setup steps after MFA return `403 mfa_enrollment_required`, the admin has not completed `/api/v1/setup/step/mfa/verify`.
- If the admin lost recovery codes after completing setup, use the existing admin MFA reset path for the tenant-scoped user identity.
- Never bypass the MFA step for a tenant admin role.

## Diagnose Missing Default Workspace

1. Check whether the user is active and has no default workspace.
2. Confirm `accounts-default-workspace-auto-create` is registered in the scheduler profile.
3. Check `SIGNUP_AUTO_CREATE_RETRY_SECONDS`; default is 30 seconds.
4. Inspect logs for `Default workspace retry failed`.

The signup verification path deliberately rolls forward even if workspace provisioning fails; the retry job owns the recovery path.

## Cross-Tenant Invitation Acceptance

Users with the same email in multiple tenants have independent user rows, credentials, MFA state, and sessions. If a user is signed in to a different tenant while accepting an invitation, the API returns `cross_tenant_invite_acceptance_blocked`; have them sign out of the other tenant and accept from the inviting tenant subdomain.
