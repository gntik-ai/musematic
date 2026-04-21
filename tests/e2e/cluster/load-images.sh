#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-amp-e2e}"

images=(
  "ghcr.io/musematic/control-plane:local|apps/control-plane/Dockerfile|apps/control-plane"
  "ghcr.io/musematic/ui:local|apps/web/Dockerfile|."
  "ghcr.io/musematic/runtime-controller:local|services/runtime-controller/Dockerfile|services/runtime-controller"
  "ghcr.io/musematic/reasoning-engine:local|services/reasoning-engine/Dockerfile|services/reasoning-engine"
  "ghcr.io/musematic/sandbox-manager:local|services/sandbox-manager/Dockerfile|services/sandbox-manager"
  "ghcr.io/musematic/simulation-controller:local|services/simulation-controller/Dockerfile|services/simulation-controller"
)

for spec in "${images[@]}"; do
  IFS='|' read -r image dockerfile context <<<"${spec}"
  echo "[e2e] building ${image} from ${dockerfile} (context: ${context})"
  docker build -t "${image}" -f "${ROOT_DIR}/${dockerfile}" "${ROOT_DIR}/${context}"
  echo "[e2e] loading ${image} into kind cluster ${CLUSTER_NAME}"
  kind load docker-image "${image}" --name "${CLUSTER_NAME}"
done
