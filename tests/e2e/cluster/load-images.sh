#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-amp-e2e}"

images=(
  "ghcr.io/musematic/control-plane:local apps/control-plane"
  "ghcr.io/musematic/ui:local apps/web"
  "ghcr.io/musematic/runtime-controller:local services/runtime-controller"
  "ghcr.io/musematic/reasoning-engine:local services/reasoning-engine"
  "ghcr.io/musematic/sandbox-manager:local services/sandbox-manager"
  "ghcr.io/musematic/simulation-controller:local services/simulation-controller"
)

for spec in "${images[@]}"; do
  image="${spec%% *}"
  context="${spec#* }"
  echo "[e2e] building ${image} from ${context}"
  docker build -t "${image}" "${ROOT_DIR}/${context}"
  echo "[e2e] loading ${image} into kind cluster ${CLUSTER_NAME}"
  kind load docker-image "${image}" --name "${CLUSTER_NAME}"
done
