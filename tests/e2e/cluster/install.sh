#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CLUSTER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-amp-e2e}"
RELEASE_NAME="${RELEASE_NAME:-amp}"
NAMESPACE="${NAMESPACE:-platform}"
PORT_UI="${PORT_UI:-8080}"
PORT_API="${PORT_API:-8081}"
PORT_WS="${PORT_WS:-8082}"
SKIP_LOAD_IMAGES="${SKIP_LOAD_IMAGES:-false}"
COMPOSITE_CHART_DIR="${ROOT_DIR}/deploy/helm/platform"
KIND_CONFIG_TEMPLATE="${CLUSTER_DIR}/kind-config.yaml"
KIND_CONFIG_PATH="${KIND_CONFIG_PATH:-/tmp/kind-config-${CLUSTER_NAME}.yaml}"
VALUES_FILE="${CLUSTER_DIR}/values-e2e.yaml"
CNPG_MANIFEST_URL="${CNPG_MANIFEST_URL:-https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.27/releases/cnpg-1.27.0.yaml}"
STRIMZI_MANIFEST_URL="${STRIMZI_MANIFEST_URL:-https://strimzi.io/install/latest?namespace=strimzi-system}"
HELM_TIMEOUT="${HELM_TIMEOUT:-20m}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[e2e] missing required command: $1" >&2
    exit 1
  fi
}

version_ge() {
  [ "$(printf '%s
%s
' "$2" "$1" | sort -V | head -n1)" = "$2" ]
}

check_version() {
  local name="$1"
  local actual="$2"
  local minimum="$3"
  if ! version_ge "$actual" "$minimum"; then
    echo "[e2e] ${name} ${actual} is below required version ${minimum}" >&2
    exit 1
  fi
}

check_prereqs() {
  require_command docker
  require_command kind
  require_command kubectl
  require_command helm
  require_command python3
  require_command envsubst
  check_version "kind" "$(kind version | sed -E 's/.*v([0-9]+\.[0-9]+\.[0-9]+).*/\1/')" "0.23.0"
  check_version "kubectl" "$(kubectl version --client -o json | python3 -c 'import json,sys; print(json.load(sys.stdin)["clientVersion"]["gitVersion"].lstrip("v"))')" "1.28.0"
  check_version "helm" "$(helm version --template '{{ .Version }}' | sed 's/^v//')" "3.14.0"
  check_version "docker" "$(docker version --format '{{.Client.Version}}')" "24.0.0"
}

render_kind_config() {
  CLUSTER_NAME="$CLUSTER_NAME" PORT_UI="$PORT_UI" PORT_API="$PORT_API" PORT_WS="$PORT_WS" envsubst < "$KIND_CONFIG_TEMPLATE" > "$KIND_CONFIG_PATH"
}

ensure_cluster() {
  render_kind_config
  if kind get clusters | grep -Fxq "${CLUSTER_NAME}"; then
    echo "[e2e] kind cluster ${CLUSTER_NAME} already exists"
    return
  fi
  echo "[e2e] creating kind cluster ${CLUSTER_NAME}"
  kind create cluster --name "${CLUSTER_NAME}" --config "${KIND_CONFIG_PATH}"
}

install_cnpg_operator() {
  echo "[e2e] installing CloudNativePG operator"
  kubectl apply --server-side=true --force-conflicts -f "${CNPG_MANIFEST_URL}"
  kubectl wait --for=condition=Available deployment/cnpg-controller-manager -n cnpg-system --timeout=300s
}

install_strimzi_operator() {
  echo "[e2e] installing Strimzi operator"
  kubectl create namespace strimzi-system --dry-run=client -o yaml | kubectl apply -f -
  kubectl apply --server-side=true --force-conflicts -n strimzi-system -f "${STRIMZI_MANIFEST_URL}"
  kubectl wait --for=condition=Available deployment/strimzi-cluster-operator -n strimzi-system --timeout=300s
}

install_platform() {
  if [[ ! -f "${COMPOSITE_CHART_DIR}/Chart.yaml" ]]; then
    echo "[e2e] missing Helm chart: ${COMPOSITE_CHART_DIR}/Chart.yaml" >&2
    exit 2
  fi

  helm dependency build "${COMPOSITE_CHART_DIR}"
  helm upgrade --install "${RELEASE_NAME}" "${COMPOSITE_CHART_DIR}" \
    -f "${VALUES_FILE}" \
    --namespace "${NAMESPACE}" \
    --create-namespace \
    --timeout "${HELM_TIMEOUT}"
}

wait_for_rollouts() {
  kubectl wait --for=condition=Ready pod --all -n "${NAMESPACE}" --timeout=300s
  kubectl wait --for=condition=Ready pod --all -n platform-data --timeout=300s
  kubectl rollout status deployment/"${RELEASE_NAME}"-control-plane-api -n "${NAMESPACE}" --timeout=300s
  kubectl rollout status deployment/"${RELEASE_NAME}"-control-plane-ws-hub -n "${NAMESPACE}" --timeout=300s
  kubectl rollout status deployment/"${RELEASE_NAME}"-ui -n "${NAMESPACE}" --timeout=300s
}

seed_baseline() {
  (
    cd "${ROOT_DIR}/tests/e2e"
    python3 -m seeders.base --all
  )
}

main() {
  check_prereqs
  ensure_cluster
  install_cnpg_operator
  install_strimzi_operator
  if [[ "${SKIP_LOAD_IMAGES}" != "true" ]]; then
    "${CLUSTER_DIR}/load-images.sh"
  fi
  install_platform
  wait_for_rollouts
  seed_baseline
  cat <<EOF
[e2e] environment ready
  UI:  http://localhost:${PORT_UI}
  API: http://localhost:${PORT_API}
  WS:  ws://localhost:${PORT_WS}
EOF
}

main "$@"
