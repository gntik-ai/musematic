# OAuth Bootstrap

## Symptom

An operator wants Google or GitHub OAuth ready immediately after a GitOps install, without a manual admin configuration step.

## Diagnosis

Check the rendered control-plane Deployment for `PLATFORM_OAUTH_GOOGLE_*` or `PLATFORM_OAUTH_GITHUB_*` variables. `PLATFORM_OAUTH_*_ENABLED=true` requires a client ID, a redirect URI, and exactly one client-secret source.

Valid secret input paths, in precedence order:

1. `PLATFORM_OAUTH_*_CLIENT_SECRET` from a Kubernetes Secret environment entry.
2. `PLATFORM_OAUTH_*_CLIENT_SECRET_FILE` from a mounted Secret file.
3. Helm `clientSecretRef.name` and `clientSecretRef.key`, rendered as the `_FILE` path.
4. `clientSecretVaultPath` for a pre-populated Vault KV v2 secret.

If no secret path resolves, bootstrap fails closed and the pod exits non-zero.

## Remediation

For the standalone control-plane chart, set `oauth.google.*` or `oauth.github.*`. For the umbrella platform chart, set the aliased dependency block `controlPlane.oauth.*`.

```yaml
controlPlane:
  oauth:
    google:
      enabled: true
      clientId: test.apps.googleusercontent.com
      clientSecretRef:
        name: google-oauth
        key: client-secret
      redirectUri: https://app.example.com/auth/oauth/google/callback
      allowedDomains:
        - example.com
      defaultRole: member
```

Apply with Helm or ArgoCD, then restart the control-plane pod if the values were changed outside the normal rollout path.

## Verification

Verify the admin OAuth tab shows `source: env_var`, the public login and signup pages render the provider button, and Vault contains `secret/data/musematic/{environment}/oauth/{provider}/client-secret`.

Run:

```bash
kubectl logs deploy/platform-control-plane-api | rg "auth.oauth.provider_bootstrapped|auth.oauth.bootstrap_skipped"
```

No log line should include a plaintext client secret.

## Rollback

Set `enabled: false` for the provider to hide the login/signup button. This does not delete the provider row or Vault secret. Delete or rotate the upstream OAuth app secret separately if the credential should be revoked.
