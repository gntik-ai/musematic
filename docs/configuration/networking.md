# Networking

Musematic assumes a default-deny network posture for sensitive namespaces and explicit ingress for user-facing services.

## Ingress

- `app.musematic.ai` routes to the web UI.
- `api.musematic.ai` routes to control-plane API and WebSocket upgrade paths.
- `grafana.musematic.ai` routes to Grafana with admin-controlled auth.

## Firewall Rules

Expose only HTTPS, SSH from operator CIDRs, and Kubernetes control-plane ports needed by the chosen deployment model. Data stores should not be publicly reachable.

## CORS

CORS must allow the configured app origin and reject unknown origins. Development origins should be separate from production origins.

## NetworkPolicy

Production namespaces should deny default egress and allow only required dependencies: API to data stores, runtime services to control plane and object storage, Promtail to Loki, metrics scrape paths, and DNS. Sandboxes should use deny-all production egress unless a workflow explicitly requires controlled access.
