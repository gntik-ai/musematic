# Quickstart: Extended E2E Journey and Observability Bundle

## First 30 Minutes

1. Install the E2E observability preset:

   ```sh
   helm dependency build deploy/helm/observability
   helm upgrade --install observability deploy/helm/observability \
     --namespace platform-observability \
     --create-namespace \
     -f deploy/helm/observability/values-e2e.yaml \
     --wait
   ```

2. Start the full E2E environment:

   ```sh
   cd tests/e2e
   make e2e-up
   ```

3. Verify the backends through their forwarded local ports:

   ```sh
   curl -fsS http://localhost:3000/api/health
   curl -fsS http://localhost:9090/-/ready
   curl -fsS http://localhost:3100/ready
   curl -fsS http://localhost:14269/
   ```

4. Run the administrator journey and bounded-context suites:

   ```sh
   make e2e-j01
   make e2e-test
   ```

5. Run chaos scenarios:

   ```sh
   make e2e-chaos
   ```

6. Inspect reports in `tests/e2e/reports/`. Dashboard snapshots are written under
   `tests/e2e/reports/snapshots/` when the Grafana renderer is enabled. The E2E
   preset disables the renderer for memory budget reasons, so snapshot helpers
   must degrade gracefully.

## Dashboard Count

The current chart ships 23 dashboard ConfigMaps. Feature 085 originally planned
for 22 after adding `trust-content-moderation.yaml`; feature 083 later added
`localization.yaml`. The canonical inventory is
`specs/085-extended-e2e-journey/contracts/dashboard-inventory.md`.
