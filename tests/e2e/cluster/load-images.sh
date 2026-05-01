#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-amp-e2e}"
DOCKER_BUILD_CACHE_DIR="${DOCKER_BUILD_CACHE_DIR:-}"
DOCKER_BUILD_CACHE_MODE="${DOCKER_BUILD_CACHE_MODE:-min}"
DOCKER_BUILD_PROGRESS="${DOCKER_BUILD_PROGRESS:-auto}"

if [[ -z "${DOCKER_BUILD_CACHE_DIR}" ]]; then
  DOCKER_CONFIG="${DOCKER_CONFIG:-/tmp/musematic-docker-config}"
  BUILDX_CONFIG="${BUILDX_CONFIG:-${DOCKER_CONFIG}/buildx}"
  export DOCKER_CONFIG BUILDX_CONFIG
  mkdir -p "${DOCKER_CONFIG}" "${BUILDX_CONFIG}/activity"
fi

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

prune_local_docker_cache() {
  if [[ "${PRUNE_DOCKER_CACHE}" != "1" ]]; then
    return
  fi

  docker image prune -af >/dev/null 2>&1 || true
  docker builder prune -af >/dev/null 2>&1 || true
}

build_image() {
  local image="$1"
  local dockerfile="$2"
  local context="$3"
  local dockerfile_path="${ROOT_DIR}/${dockerfile}"
  local context_path="${ROOT_DIR}/${context}"

  if [[ -n "${DOCKER_BUILD_CACHE_DIR}" ]] && docker buildx version >/dev/null 2>&1; then
    local cache_scope="${image//\//_}"
    cache_scope="${cache_scope//:/_}"
    local cache_src="${DOCKER_BUILD_CACHE_DIR}/${cache_scope}"
    local cache_dst="${DOCKER_BUILD_CACHE_DIR}.new/${cache_scope}"
    local cache_args=(
      --cache-to "type=local,dest=${cache_dst},mode=${DOCKER_BUILD_CACHE_MODE}"
    )
    mkdir -p "${cache_src}" "$(dirname "${cache_dst}")"
    rm -rf "${cache_dst}"
    if [[ -f "${cache_src}/index.json" ]]; then
      cache_args=(--cache-from "type=local,src=${cache_src}" "${cache_args[@]}")
    fi
    docker buildx build \
      --load \
      --progress="${DOCKER_BUILD_PROGRESS}" \
      "${cache_args[@]}" \
      -t "${image}" \
      -f "${dockerfile_path}" \
      "${context_path}"
    rm -rf "${cache_src}"
    mv "${cache_dst}" "${cache_src}"
    return
  fi

  DOCKER_BUILDKIT=1 docker build --rm --force-rm -t "${image}" -f "${dockerfile_path}" "${context_path}"
}

if [[ "${PRUNE_DOCKER_CACHE}" == "1" ]]; then
  echo "[e2e] pruning local Docker caches before image builds"
  prune_local_docker_cache
fi

for spec in "${images[@]}"; do
  IFS='|' read -r image dockerfile context <<<"${spec}"
  if [[ -n "${IMAGE_FILTER}" && "${image}" != *"${IMAGE_FILTER}"* ]]; then
    continue
  fi
  echo "[e2e] building ${image} from ${dockerfile} (context: ${context})"
  build_image "${image}" "${dockerfile}" "${context}"
  echo "[e2e] loading ${image} into kind cluster ${CLUSTER_NAME}"
  kind load docker-image "${image}" --name "${CLUSTER_NAME}"
  docker image rm -f "${image}" >/dev/null 2>&1 || true
  if [[ "${PRUNE_DOCKER_CACHE}" == "1" ]]; then
    echo "[e2e] pruning local Docker caches after loading ${image}"
    prune_local_docker_cache
  fi
done

docker system df || true
