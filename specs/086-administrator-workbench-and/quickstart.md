# Quickstart: Administrator Workbench First 30 Minutes

## 1. Install With Headless Super Admin Bootstrap

Create a Kubernetes Secret that contains the one-time bootstrap password:

```sh
kubectl -n platform create secret generic test-superadmin \
  --from-literal=password='replace-with-sealed-secret-value'
```

Install or upgrade the platform chart with the bootstrap values:

```sh
helm upgrade --install musematic deploy/helm/platform \
  --namespace platform --create-namespace \
  --set superadmin.username=alice \
  --set superadmin.email=alice@example.com \
  --set superadmin.passwordSecretRef=test-superadmin \
  --set superadmin.mfaEnrollment=required_before_first_login \
  --set platformInstanceName="Musematic Platform" \
  --set tenantMode=single
```

The post-install/post-upgrade bootstrap Job runs `python -m platform.admin.bootstrap`. Re-running the same install is idempotent. Production password resets require both `PLATFORM_FORCE_RESET_SUPERADMIN=true` and `ALLOW_SUPERADMIN_RESET=true`.

## 2. Log In And Complete First Install

Open `/login`, sign in as the bootstrapped super admin, and follow `/admin`:

- Verify instance settings.
- Configure OAuth providers if required.
- Invite a second admin.
- Verify observability health.
- Run or verify the first backup.
- Review security settings.
- Enroll MFA.

Checklist state persists on the user row in `users.first_install_checklist_state`.

## 3. Exercise Core Admin Controls

- Visit `/admin/users` and confirm tenant-scoped user visibility.
- Visit `/admin/settings` and update one non-secret platform setting.
- Visit `/admin/regions` as a super admin and initiate a 2PA failover request.
- Approve the request from a different super admin account.
- Start and end an impersonation session with a support justification of at least 20 characters.
- Toggle read-only mode and verify non-GET `/api/v1/admin/*` requests return `admin_read_only_mode`.

## 4. Export Configuration

Open `/admin/lifecycle/installer`, choose **Export configuration**, and store the signed tarball in the deployment change record. Secrets are omitted or represented as references only. Use **Import configuration** in a target environment to preview diffs before applying with the typed phrase `IMPORT CONFIG`.
