# Helm Snapshot Workflow — Contributor Guide

**Owner**: Platform / DevX
**Feature**: UPD-053 (106) US6 — chart-change CI gate
**Last updated**: 2026-05-05

The Helm chart at `deploy/helm/platform/` ships with two **rendered
snapshots** committed into the repo:

```text
deploy/helm/platform/.snapshots/
├── prod.rendered.yaml
└── dev.rendered.yaml
```

Each is the verbatim output of `helm template release ... -f
values.{prod,dev}.yaml`. CI re-renders both on every PR that touches
`deploy/helm/**` and **fails** if the result differs from the committed
snapshot. The intent is twofold:

1. **Reviewers see the rendered diff** in the PR alongside the source
   change — it makes intent obvious in a way `helm template | diff`
   never quite did.
2. **Drift is a deliberate, tracked decision**. Forgetting to update the
   snapshot is a CI failure; updating it without a corresponding source
   change is a CI failure on the next PR (the snapshot drifts back).

---

## When you've changed the chart

After every change to `deploy/helm/platform/templates/`,
`deploy/helm/platform/values{,.prod,.dev}.yaml`, or `Chart.yaml`:

```sh
make helm-snapshot-update
```

This regenerates both `.snapshots/prod.rendered.yaml` and
`.snapshots/dev.rendered.yaml` from the current chart against
`values.{prod,dev}.yaml`. The Makefile target is the source of truth
for the render command — keep it in sync with the CI step in
`.github/workflows/ci.yml` `helm-lint > Render Helm snapshots`.

Inspect the diff and confirm it matches your intent:

```sh
git diff deploy/helm/platform/.snapshots/
```

Then commit the regenerated files in the **same** PR as the chart
change. Reviewers reading the PR will see exactly how the rendered
output changed.

---

## When CI fails with "snapshot drift"

The CI step's error message tells you which env drifted. Reproduce
locally:

```sh
make helm-snapshot-update
git diff deploy/helm/platform/.snapshots/
```

Two possibilities:

1. **You forgot to regenerate.** `git diff` shows the rendered changes
   that match the source change in your branch. Commit them.

2. **Someone else regenerated against a different chart state.** Rebase
   onto `main`, re-run `make helm-snapshot-update`, and resolve the
   diff. The rendered output is fully derived from sources, so you
   never need a 3-way merge — always re-render.

---

## Why this gate exists

Helm template changes can ripple through dozens of resources in
hundreds of lines of YAML. Reviewing source-only changes in a
`templates/foo.yaml` diff doesn't show what the operator's cluster
actually receives. The committed snapshots make every reviewable PR
self-contained: source change + rendered effect, side by side.

The same gate also catches accidental Helm dependency rebuilds: when
`Chart.lock` updates, the rendered output usually shifts in subtle
ways (image digests, chart-of-charts metadata) that a reviewer would
otherwise need to spot by hand.

---

## Local smoke test

`tests/ci/test_helm_snapshot_drift.py` runs the same regenerate-and-diff
cycle and is opt-in via `RUN_HELM_SNAPSHOT_DRIFT=1`:

```sh
RUN_HELM_SNAPSHOT_DRIFT=1 pytest tests/ci/test_helm_snapshot_drift.py -v
```

Run it before pushing a chart change to catch the drift before CI does.

---

## Cross-references

- `specs/106-hetzner-clusters/contracts/ci-helm-snapshot.md` (CI gates contract; lives in the repo root, outside the docs site)
- [Hetzner cluster provisioning](./hetzner-cluster-provisioning.md)
- [Wildcard TLS renewal](./wildcard-tls-renewal.md)
- [Cloudflare Pages status](./cloudflare-pages-status.md)
