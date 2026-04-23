#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-amp-e2e}"
DOCKER_CONFIG="${DOCKER_CONFIG:-/tmp/musematic-docker-config}"
BUILDX_CONFIG="${BUILDX_CONFIG:-${DOCKER_CONFIG}/buildx}"
export DOCKER_CONFIG BUILDX_CONFIG
mkdir -p "${DOCKER_CONFIG}" "${BUILDX_CONFIG}/activity"

images=(
  "ghcr.io/musematic/control-plane:local|apps/control-plane/Dockerfile|apps/control-plane"
  "ghcr.io/musematic/ui:local|apps/web/Dockerfile|."
  "ghcr.io/musematic/runtime-controller:local|services/runtime-controller/Dockerfile|services/runtime-controller"
  "ghcr.io/musematic/reasoning-engine:local|services/reasoning-engine/Dockerfile|services/reasoning-engine"
  "ghcr.io/musematic/sandbox-manager:local|services/sandbox-manager/Dockerfile|services/sandbox-manager"
  "ghcr.io/musematic/simulation-controller:local|services/simulation-controller/Dockerfile|services/simulation-controller"
  "ghcr.io/musematic/mock-google-oidc:local|services/mock-google-oidc/Dockerfile|services/mock-google-oidc"
  "ghcr.io/musematic/mock-github-oauth:local|services/mock-github-oauth/Dockerfile|services/mock-github-oauth"
)
PRUNE_DOCKER_CACHE="${PRUNE_DOCKER_CACHE:-1}"
IMAGE_FILTER="${IMAGE_FILTER:-}"

for spec in "${images[@]}"; do
  IFS='|' read -r image dockerfile context <<<"${spec}"
  if [[ -n "${IMAGE_FILTER}" && "${image}" != *"${IMAGE_FILTER}"* ]]; then
    continue
  fi
  echo "[e2e] building ${image} from ${dockerfile} (context: ${context})"
  docker build --rm --force-rm -t "${image}" -f "${ROOT_DIR}/${dockerfile}" "${ROOT_DIR}/${context}"
  echo "[e2e] loading ${image} into kind cluster ${CLUSTER_NAME}"
  kind load docker-image "${image}" --name "${CLUSTER_NAME}"
  docker image rm -f "${image}" >/dev/null 2>&1 || true
done

if [[ "${PRUNE_DOCKER_CACHE}" == "1" ]]; then
  echo "[e2e] pruning local Docker caches after loading all images"
  docker image prune -af >/dev/null 2>&1 || true
  docker builder prune -af >/dev/null 2>&1 || true
fi

docker system df || true
