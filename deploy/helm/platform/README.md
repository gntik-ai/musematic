# Platform Helm Chart

## OAuth Provider Redirects

Google and GitHub provider consoles should continue to use the backend callback
URL:

```text
https://<platform-api-host>/api/v1/auth/oauth/{provider}/callback
```

UPD-037 changes only the frontend handoff after the backend has validated the
OAuth callback. Successful and failed browser flows now land on:

```text
https://<platform-web-host>/auth/oauth/{provider}/callback
```

No Google or GitHub console reconfiguration is needed for this frontend callback
page. Keep the backend `redirect_uri` value configured in the admin OAuth
provider settings and chart values.
