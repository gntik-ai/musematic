# Contract — cert-manager ClusterIssuer + Certificate templates

Three new templates under `deploy/helm/platform/templates/`. All gated by `.Values.certManager.enabled`. They depend on the `cert-manager` and `cert-manager-webhook-hetzner` Helm sub-dependencies that UPD-053 adds to `Chart.yaml`.

## `templates/certmanager-clusterissuer.yaml`

```yaml
{{- if .Values.certManager.enabled }}
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: {{ .Values.certManager.clusterIssuer.name }}
  labels:
    {{- include "platform.labels" . | nindent 4 }}
spec:
  acme:
    email: {{ .Values.certManager.clusterIssuer.email }}
    server: {{ .Values.certManager.clusterIssuer.server }}
    privateKeySecretRef:
      name: {{ .Values.certManager.clusterIssuer.name }}-private-key
    solvers:
      - dns01:
          webhook:
            groupName: {{ .Values.certManager.hetznerDnsWebhook.groupName | default "acme.musematic.ai" }}
            solverName: hetzner
            config:
              secretName: {{ .Values.hetzner.dns.apiTokenSecretRef.name }}
              zoneName: {{ .Values.hetzner.dns.zone }}
              apiUrl: https://dns.hetzner.com/api/v1
{{- end }}
```

## `templates/certmanager-certificate-wildcard.yaml`

Renders one `Certificate` per entry in `.Values.certManager.certificates`:

```yaml
{{- if .Values.certManager.enabled }}
{{- range .Values.certManager.certificates }}
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: {{ .name }}
  namespace: {{ $.Release.Namespace }}
  labels:
    {{- include "platform.labels" $ | nindent 4 }}
spec:
  secretName: {{ .secretName }}
  issuerRef:
    name: {{ $.Values.certManager.clusterIssuer.name }}
    kind: ClusterIssuer
  dnsNames:
    {{- toYaml .dnsNames | nindent 4 }}
  renewBefore: {{ .renewBefore | default "720h" }}
  privateKey:
    algorithm: ECDSA
    size: 256
    rotationPolicy: Always
{{- end }}
{{- end }}
```

The wildcard cert and the apex cert can both be expressed as entries in `certificates`; in practice the spec collapses them into a single entry per env (`dnsNames: ["*.musematic.ai", "musematic.ai"]`) because Let's Encrypt issues a single cert for the SAN list, which is more rate-limit-efficient than two certs.

## `templates/service-loadbalancer.yaml`

NEW — renders the Service of type `LoadBalancer` for the ingress controller with Hetzner Cloud Controller Manager annotations. Replaces any operator-side manual annotation that exists today.

```yaml
{{- if and .Values.hetzner .Values.hetzner.loadBalancer }}
apiVersion: v1
kind: Service
metadata:
  name: ingress-nginx-controller
  namespace: ingress-nginx
  annotations:
    load-balancer.hetzner.cloud/location:              {{ .Values.hetzner.loadBalancer.location | quote }}
    load-balancer.hetzner.cloud/network-zone:          {{ .Values.hetzner.loadBalancer.networkZone | quote }}
    load-balancer.hetzner.cloud/use-private-ip:        {{ .Values.hetzner.loadBalancer.usePrivateIp | toString | quote }}
    load-balancer.hetzner.cloud/uses-proxyprotocol:    {{ .Values.hetzner.loadBalancer.proxyProtocol | toString | quote }}
    load-balancer.hetzner.cloud/name:                  {{ .Values.hetzner.loadBalancer.name | quote }}
    load-balancer.hetzner.cloud/type:                  {{ .Values.hetzner.loadBalancer.type | quote }}
    load-balancer.hetzner.cloud/protocol:              "tcp"
    load-balancer.hetzner.cloud/health-check-protocol: "tcp"
spec:
  type: LoadBalancer
  externalTrafficPolicy: Local
  ports:
    - { name: http,  port: 80,  protocol: TCP, targetPort: http  }
    - { name: https, port: 443, protocol: TCP, targetPort: https }
  selector:
    app.kubernetes.io/name: ingress-nginx
{{- end }}
```

## `templates/ingress-platform.yaml` (EXTEND existing)

The existing `ingress.hosts` rules are preserved verbatim. UPD-053 adds a wildcard rule block that renders only when `ingress.wildcardHosts` is non-empty:

```yaml
# (existing rules here — apex/app/api/grafana — unchanged)
{{- range .Values.ingress.wildcardHosts }}
- host: {{ . }}
  http:
    paths:
      - path: /api/
        pathType: Prefix
        backend:
          service:
            name: control-plane-service
            port: { number: 80 }
      - path: /
        pathType: Prefix
        backend:
          service:
            name: frontend-service
            port: { number: 80 }
{{- end }}
```

The hostname-extraction middleware (UPD-046) handles the actual tenant-slug-from-Host parsing inside the control plane and the frontend.

## Helm dependencies

`deploy/helm/platform/Chart.yaml` gains two conditional dependencies:

```yaml
dependencies:
  - name: cert-manager
    version: v1.16.0
    repository: https://charts.jetstack.io
    condition: certManager.enabled
  - name: cert-manager-webhook-hetzner
    version: 0.6.0
    repository: https://vadimkim.github.io/cert-manager-webhook-hetzner
    condition: certManager.hetznerDnsWebhook.enabled
```

`helm dependency update deploy/helm/platform` runs as part of the documented operator setup and as part of the CI `helm-lint` job (already present at `.github/workflows/ci.yml:1097` — `helm dependency build "$chart"`).

## Vault → Kubernetes Secret sync

The `hetzner-dns-token` Secret consumed by both the cert-manager Hetzner DNS-01 webhook AND `tenants/dns_automation.py` is synced from Vault by the existing `vault/` chart pattern (`VaultStaticSecret` CRD from `external-secrets` operator, already deployed via `deploy/helm/vault/`). UPD-053 adds one new `VaultStaticSecret` template:

```yaml
{{- if .Values.certManager.enabled }}
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: hetzner-dns-token
  namespace: {{ .Release.Namespace }}
spec:
  refreshInterval: 1h
  secretStoreRef:
    kind: ClusterSecretStore
    name: vault-cluster-store           # already exists from UPD-040
  target:
    name: {{ .Values.hetzner.dns.apiTokenSecretRef.name }}
  data:
    - secretKey: {{ .Values.hetzner.dns.apiTokenSecretRef.key }}
      remoteRef:
        key: musematic/{{ .Values.environment | default "prod" }}/dns/hetzner/api-token
        property: token
{{- end }}
```

Token rotation flow: operator runs `vault kv put secret/musematic/prod/dns/hetzner/api-token token=$NEW`; ExternalSecret reconciles within `refreshInterval` (1h ceiling, 1m on next change detection); cert-manager webhook and `dns_automation.py` re-read on next call. No restart needed for `dns_automation.py` because it pulls the token through `SecretProvider` per request (with a short-lived in-process cache).
