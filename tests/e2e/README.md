# E2E Harness on kind

This harness provisions a local end-to-end environment on kind and runs bounded-context,
chaos, and performance checks against a live platform deployment.

## Prerequisites

- Docker >= 24
- kind >= 0.23
- kubectl >= 1.28
- Helm >= 3.14
- Python >= 3.12

## Main commands

```bash
cd tests/e2e
make e2e-check
make e2e-up
make e2e-test
make e2e-chaos
make e2e-perf
make e2e-down
```

## Acceptance scenarios

The expected flows for provisioning, suites, chaos, performance, CI, and parallel
clusters are documented in [quickstart.md](../../specs/071-e2e-kind-testing/quickstart.md).

## API contracts

- [E2E endpoints](../../specs/071-e2e-kind-testing/contracts/e2e-endpoints.md)
- [Fixtures API](../../specs/071-e2e-kind-testing/contracts/fixtures-api.md)
- [Helm overlay](../../specs/071-e2e-kind-testing/contracts/helm-overlay.md)

## Troubleshooting

- If kind fails because ports are already bound, change `PORT_UI`, `PORT_API`, and `PORT_WS`.
- If Docker image builds exhaust memory, close other containers and retry before recreating the cluster.
- If cluster bring-up fails, run `tests/e2e/cluster/capture-state.sh` to collect pod, event, and log output.
