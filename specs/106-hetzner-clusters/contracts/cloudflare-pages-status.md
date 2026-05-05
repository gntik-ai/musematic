# Contract — Cloudflare Pages status page push

UPD-053 satisfies constitution rule 49 (status page operational independence) for production by deploying `status.musematic.ai` on **Cloudflare Pages** rather than inside the platform Kubernetes cluster. Dev keeps the existing in-cluster status deployment for cost (research R6).

## Out-of-band setup (operator runbook)

Operator-side, before `helm install`:

1. Create a Cloudflare Pages project named `status-musematic-ai`.
2. Issue a Cloudflare API token scoped to `Pages:Edit` for the project + `DNS:Edit` for `musematic.ai` (for CNAME flattening on the apex `status.musematic.ai`).
3. Store the token in Vault: `vault kv put secret/musematic/prod/cloudflare/pages-token token=$TOKEN`.
4. Provision the CNAME `status.musematic.ai → status-musematic-ai.pages.dev` (or via Cloudflare Pages custom-domain wizard).

The runbook at `docs/operations/cloudflare-pages-status.md` (NEW) walks through these steps end-to-end with screenshots.

## Push pipeline (in-cluster CronJob)

The existing `templates/status-snapshot-cronjob.yaml` is **extended** to add a push-to-Cloudflare-Pages branch gated by `webStatus.deployedHere=false` AND `webStatus.pushDestination=cloudflare-pages`:

```yaml
{{- if .Values.webStatus.enabled }}
{{- if and (not .Values.webStatus.deployedHere) (eq .Values.webStatus.pushDestination "cloudflare-pages") }}
apiVersion: batch/v1
kind: CronJob
metadata:
  name: {{ .Release.Name }}-status-pages-push
  namespace: platform-edge
spec:
  schedule: "*/1 * * * *"               # every minute (the regenerator runs every 30s; CronJob runs at coarsest viable granularity)
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: push
              image: ghcr.io/cloudflare/wrangler:latest
              env:
                - name: CLOUDFLARE_API_TOKEN
                  valueFrom: { secretKeyRef: { name: cloudflare-pages-token, key: token } }
                - name: STATUS_API_INTERNAL_URL
                  value: {{ .Values.webStatus.statusApiInternalUrl | quote }}
                - name: PUSH_INTERVAL_SECONDS
                  value: {{ .Values.webStatus.pushIntervalSeconds | quote }}
              command: ["/bin/sh", "-ec"]
              args:
                - |
                  set -eu
                  workdir=$(mktemp -d)
                  # Loop within the minute so we can do multiple pushes per CronJob tick
                  iters=$(( 60 / ${PUSH_INTERVAL_SECONDS:-30} ))
                  for i in $(seq 1 $iters); do
                    curl -fsS "${STATUS_API_INTERNAL_URL}/api/v1/internal/status_page/render" -o "$workdir/index.html"
                    wrangler pages deploy "$workdir" \
                      --project-name="{{ .Values.webStatus.cloudflarePages.projectName }}" \
                      --branch=main
                    sleep ${PUSH_INTERVAL_SECONDS:-30}
                  done
{{- end }}
{{- end }}
```

## Failure & alerting

- **Push fails**: the next CronJob tick retries. If 10 consecutive ticks fail (≈10 minutes), the Prometheus alert `StatusPagePushStuck` (NEW alert in `deploy/helm/observability/`) fires — page on-call.
- **Page goes stale**: the Cloudflare Pages deployment carries the timestamp of the last successful render in a `<meta>` tag; a Cloudflare Worker on the page surfaces a "last updated X minutes ago" badge so external readers can detect stale content (FR-789).
- **Cloudflare Pages outage**: the runbook documents the fallback — switch DNS for `status.musematic.ai` from the Cloudflare Pages CNAME to a static `nginx` Hetzner Cloud VM running an `index.html` rendered by an emergency `wrangler pages download` snapshot or a pre-provisioned VM. The fallback IPv4/IPv6 are recorded in `terraform/environments/production/terraform.tfvars.example` so the failover DNS swap is one record edit.

## Why a CronJob inside the platform cluster (not external)

The constraint is operational *independence of the status page surface*, not independence of the *content generator*. The content generator legitimately lives inside the platform — it's the system reporting on itself. If the platform is fully down the generator stops, but the LAST PUSHED CONTENT remains served by Cloudflare Pages with its "last updated" badge — which is the user-visible behaviour rule 49 requires.

## Dev path (in-cluster fallback)

For dev, `webStatus.deployedHere=true`, the existing in-cluster `web-status-deployment.yaml` + `web-status-ingress.yaml` are rendered (unchanged), and the Cloudflare Pages branch above is skipped. Operators monitoring dev have direct cluster access; rule 49 applies to public/customer-facing status surfaces, not to dev observability.
