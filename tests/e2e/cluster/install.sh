#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CLUSTER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-amp-e2e}"
RELEASE_NAME="${RELEASE_NAME:-amp}"
NAMESPACE="${NAMESPACE:-platform}"
PLATFORM_DATA_NAMESPACE="${PLATFORM_DATA_NAMESPACE:-platform-data}"
PLATFORM_EXECUTION_NAMESPACE="${PLATFORM_EXECUTION_NAMESPACE:-platform-execution}"
PLATFORM_SIMULATION_NAMESPACE="${PLATFORM_SIMULATION_NAMESPACE:-platform-simulation}"
KAFKA_NAMESPACE="${KAFKA_NAMESPACE:-strimzi-system}"
KAFKA_CLUSTER_NAME="${KAFKA_CLUSTER_NAME:-musematic-kafka}"
CLICKHOUSE_NAMESPACE="${CLICKHOUSE_NAMESPACE:-${NAMESPACE}}"
NEO4J_NAMESPACE="${NEO4J_NAMESPACE:-${NAMESPACE}}"
PORT_UI="${PORT_UI:-8080}"
PORT_API="${PORT_API:-8081}"
PORT_WS="${PORT_WS:-8082}"
PORT_GOOGLE_OIDC="${PORT_GOOGLE_OIDC:-8083}"
PORT_GITHUB_OAUTH="${PORT_GITHUB_OAUTH:-8084}"
PORT_VAULT="${PORT_VAULT:-30085}"
SKIP_LOAD_IMAGES="${SKIP_LOAD_IMAGES:-false}"
COMPOSITE_CHART_DIR="${ROOT_DIR}/deploy/helm/platform"
VAULT_CHART_DIR="${ROOT_DIR}/deploy/helm/vault"
VAULT_NAMESPACE="${VAULT_NAMESPACE:-platform-security}"
VAULT_RELEASE_NAME="${VAULT_RELEASE_NAME:-vault}"
VAULT_VALUES_FILE="${VAULT_VALUES_FILE:-${VAULT_CHART_DIR}/values-dev.yaml}"
PLATFORM_VAULT_MODE="${PLATFORM_VAULT_MODE:-mock}"
OBSERVABILITY_CHART_DIR="${ROOT_DIR}/deploy/helm/observability"
OBSERVABILITY_NAMESPACE="${OBSERVABILITY_NAMESPACE:-platform-observability}"
OBSERVABILITY_RELEASE_NAME="${OBSERVABILITY_RELEASE_NAME:-observability}"
OBSERVABILITY_VALUES_FILE="${OBSERVABILITY_VALUES_FILE:-${OBSERVABILITY_CHART_DIR}/values-e2e.yaml}"
OBSERVABILITY_PORT_FORWARD_DIR="${OBSERVABILITY_PORT_FORWARD_DIR:-/tmp/musematic-e2e-observability-${CLUSTER_NAME}}"
KIND_CONFIG_TEMPLATE="${CLUSTER_DIR}/kind-config.yaml"
KIND_CONFIG_PATH="${KIND_CONFIG_PATH:-/tmp/kind-config-${CLUSTER_NAME}.yaml}"
VALUES_FILE="${CLUSTER_DIR}/values-e2e.yaml"
CNPG_MANIFEST_URL="${CNPG_MANIFEST_URL:-https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.27/releases/cnpg-1.27.0.yaml}"
STRIMZI_MANIFEST_URL="${STRIMZI_MANIFEST_URL:-https://strimzi.io/install/latest?namespace=strimzi-system}"
HELM_TIMEOUT="${HELM_TIMEOUT:-20m}"
PLATFORM_READY_TIMEOUT="${PLATFORM_READY_TIMEOUT:-600s}"
POSTGRES_READY_TIMEOUT="${POSTGRES_READY_TIMEOUT:-600s}"
JOB_READY_TIMEOUT="${JOB_READY_TIMEOUT:-600s}"
MIGRATION_RETRY_ATTEMPTS="${MIGRATION_RETRY_ATTEMPTS:-60}"
MIGRATION_RETRY_DELAY_SECONDS="${MIGRATION_RETRY_DELAY_SECONDS:-5}"
CONTROL_PLANE_MIGRATION_IMAGE="${CONTROL_PLANE_MIGRATION_IMAGE:-ghcr.io/musematic/control-plane:local}"
CLICKHOUSE_SCHEMA_IMAGE="${CLICKHOUSE_SCHEMA_IMAGE:-mirror.gcr.io/clickhouse/clickhouse-server:24.3}"
NEO4J_SCHEMA_IMAGE="${NEO4J_SCHEMA_IMAGE:-mirror.gcr.io/library/neo4j:5.21.0}"
MINIO_BUCKET_INIT_IMAGE="${MINIO_BUCKET_INIT_IMAGE:-mirror.gcr.io/minio/mc:latest}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[e2e] missing required command: $1" >&2
    exit 1
  fi
}

version_ge() {
  [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]
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
  CLUSTER_NAME="$CLUSTER_NAME" PORT_UI="$PORT_UI" PORT_API="$PORT_API" PORT_WS="$PORT_WS" PORT_GOOGLE_OIDC="$PORT_GOOGLE_OIDC" PORT_GITHUB_OAUTH="$PORT_GITHUB_OAUTH" PORT_VAULT="$PORT_VAULT" envsubst < "$KIND_CONFIG_TEMPLATE" > "$KIND_CONFIG_PATH"
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

ensure_supporting_namespaces() {
  for namespace in "${PLATFORM_EXECUTION_NAMESPACE}" "${PLATFORM_SIMULATION_NAMESPACE}"; do
    kubectl create namespace "$namespace" --dry-run=client -o yaml | kubectl apply -f -
  done
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
  kubectl rollout status -n strimzi-system deployment/strimzi-cluster-operator --timeout=300s
  kubectl wait --for=condition=Available deployment/strimzi-cluster-operator -n strimzi-system --timeout=300s
}

adopt_existing_kafka_topics() {
  local selector="strimzi.io/cluster=${KAFKA_CLUSTER_NAME}"
  local topics

  if ! kubectl get kafkatopic -n "${KAFKA_NAMESPACE}" >/dev/null 2>&1; then
    return
  fi

  mapfile -t topics < <(
    kubectl get kafkatopic -n "${KAFKA_NAMESPACE}" -l "$selector" -o name 2>/dev/null || true
  )
  if [[ "${#topics[@]}" -eq 0 ]]; then
    return
  fi

  echo "[e2e] adopting existing KafkaTopic resources into Helm release ${RELEASE_NAME}"
  for topic in "${topics[@]}"; do
    kubectl label -n "${KAFKA_NAMESPACE}" "$topic" \
      app.kubernetes.io/managed-by=Helm \
      --overwrite
    kubectl annotate -n "${KAFKA_NAMESPACE}" "$topic" \
      meta.helm.sh/release-name="${RELEASE_NAME}" \
      meta.helm.sh/release-namespace="${NAMESPACE}" \
      --overwrite
  done
}

install_platform() {
  if [[ ! -f "${COMPOSITE_CHART_DIR}/Chart.yaml" ]]; then
    echo "[e2e] missing Helm chart: ${COMPOSITE_CHART_DIR}/Chart.yaml" >&2
    exit 2
  fi

  helm dependency build "${COMPOSITE_CHART_DIR}"
  helm upgrade --install "${RELEASE_NAME}" "${COMPOSITE_CHART_DIR}" \
    -f "${VALUES_FILE}" \
    --set "controlPlane.vault.mode=${PLATFORM_VAULT_MODE}" \
    --namespace "${NAMESPACE}" \
    --create-namespace \
    --timeout "${HELM_TIMEOUT}"
}

install_vault() {
  if [[ "${PLATFORM_VAULT_MODE}" != "vault" ]]; then
    return
  fi
  if [[ ! -f "${VAULT_CHART_DIR}/Chart.yaml" ]]; then
    echo "[e2e] missing Helm chart: ${VAULT_CHART_DIR}/Chart.yaml" >&2
    exit 2
  fi

  echo "[e2e] installing Vault stack"
  ensure_vault_helm_repos
  helm dependency build "${VAULT_CHART_DIR}"
  helm upgrade --install "${VAULT_RELEASE_NAME}" "${VAULT_CHART_DIR}" \
    --namespace "${VAULT_NAMESPACE}" \
    --create-namespace \
    -f "${VAULT_VALUES_FILE}" \
    --timeout "${HELM_TIMEOUT}"
  wait_for_labelled_pod "${VAULT_NAMESPACE}" "app.kubernetes.io/name=vault" "${PLATFORM_READY_TIMEOUT}"
}

ensure_vault_helm_repos() {
  helm repo add hashicorp https://helm.releases.hashicorp.com --force-update
  helm repo update
}

wait_for_observability_stack() {
  local timeout="${1:-300s}"
  local selectors=(
    "app.kubernetes.io/name=grafana"
    "app.kubernetes.io/name=prometheus"
    "app.kubernetes.io/name=loki"
    "app.kubernetes.io/name=promtail"
    "app.kubernetes.io/name=opentelemetry-collector"
    "app.kubernetes.io/name=jaeger"
  )

  for selector in "${selectors[@]}"; do
    wait_for_labelled_pod "${OBSERVABILITY_NAMESPACE}" "$selector" "$timeout"
  done
}

is_kubectl_port_forward_pid() {
  local pid="$1"
  local args

  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  args="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  [[ "$args" == *kubectl* && "$args" == *port-forward* ]]
}

reset_observability_port_forwards() {
  local pid_file
  local pid

  if [[ ! -d "${OBSERVABILITY_PORT_FORWARD_DIR}" ]]; then
    return
  fi

  for pid_file in "${OBSERVABILITY_PORT_FORWARD_DIR}"/*.pid; do
    [[ -e "$pid_file" ]] || continue
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if is_kubectl_port_forward_pid "$pid"; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done

  rm -rf "${OBSERVABILITY_PORT_FORWARD_DIR}"
}

start_observability_port_forward() {
  local name="$1"
  local target="$2"
  local local_port="$3"
  local remote_port="$4"
  local pid_file="${OBSERVABILITY_PORT_FORWARD_DIR}/${name}.pid"
  local log_file="${OBSERVABILITY_PORT_FORWARD_DIR}/${name}.log"

  if [[ -f "$pid_file" ]] && is_kubectl_port_forward_pid "$(cat "$pid_file" 2>/dev/null || true)"; then
    return
  fi
  mkdir -p "${OBSERVABILITY_PORT_FORWARD_DIR}"
  nohup kubectl -n "${OBSERVABILITY_NAMESPACE}" port-forward "$target" "${local_port}:${remote_port}" >"$log_file" 2>&1 &
  echo "$!" > "$pid_file"
}

probe_observability_http() {
  local name="$1"
  local url="$2"
  local timeout_seconds=120
  local waited=0

  while (( waited < timeout_seconds )); do
    if python3 - "$url" <<'PY' >/dev/null 2>&1
import sys
import urllib.request

with urllib.request.urlopen(sys.argv[1], timeout=3) as response:
    if response.status < 200 or response.status >= 300:
        raise SystemExit(1)
PY
    then
      return
    fi
    sleep 2
    waited=$((waited + 2))
  done

  echo "[e2e] observability endpoint ${name} failed readiness probe at ${url}" >&2
  exit 1
}

start_observability_port_forwards() {
  echo "[e2e] starting observability port-forwards under ${OBSERVABILITY_PORT_FORWARD_DIR}"
  reset_observability_port_forwards
  start_observability_port_forward loki "svc/observability-loki-gateway" 3100 80
  start_observability_port_forward prometheus "svc/observability-kube-prometh-prometheus" 9090 9090
  start_observability_port_forward grafana "svc/observability-grafana" 3000 80
  start_observability_port_forward jaeger "deployment/observability-jaeger" 14269 14269
  start_observability_port_forward otel "deployment/otel-collector" 13133 13133

  probe_observability_http loki "http://localhost:3100/loki/api/v1/status/buildinfo"
  probe_observability_http prometheus "http://localhost:9090/-/ready"
  probe_observability_http grafana "http://localhost:3000/api/health"
  probe_observability_http jaeger "http://localhost:14269/"
  probe_observability_http otel "http://localhost:13133/"
}

ensure_observability_helm_repos() {
  helm repo add opentelemetry https://open-telemetry.github.io/opentelemetry-helm-charts --force-update
  helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update
  helm repo add jaegertracing https://jaegertracing.github.io/helm-charts --force-update
  helm repo add grafana https://grafana.github.io/helm-charts --force-update
  helm repo update
}

install_observability() {
  if [[ ! -f "${OBSERVABILITY_CHART_DIR}/Chart.yaml" ]]; then
    echo "[e2e] missing Helm chart: ${OBSERVABILITY_CHART_DIR}/Chart.yaml" >&2
    exit 2
  fi

  echo "[e2e] installing observability stack"
  ensure_observability_helm_repos
  helm dependency build "${OBSERVABILITY_CHART_DIR}"
  helm upgrade --install "${OBSERVABILITY_RELEASE_NAME}" "${OBSERVABILITY_CHART_DIR}" \
    --namespace "${OBSERVABILITY_NAMESPACE}" \
    --create-namespace \
    -f "${OBSERVABILITY_VALUES_FILE}" \
    --timeout "${HELM_TIMEOUT}"
  wait_for_observability_stack "${PLATFORM_READY_TIMEOUT}"
  start_observability_port_forwards
}

wait_for_labelled_pod() {
  local namespace="$1"
  local selector="$2"
  local timeout="$3"
  local waited=0
  local sleep_seconds=5
  local timeout_seconds

  timeout_seconds="$(python3 - <<'PY' "$timeout"
import sys
value = sys.argv[1]
if value.endswith('s'):
    print(int(value[:-1]))
elif value.endswith('m'):
    print(int(value[:-1]) * 60)
else:
    raise SystemExit(f'unsupported timeout format: {value}')
PY
)"

  while (( waited < timeout_seconds )); do
    if kubectl get pods -n "$namespace" -l "$selector" -o name 2>/dev/null | grep -q .; then
      kubectl wait -n "$namespace" --for=condition=Ready pod -l "$selector" --timeout="$timeout"
      return
    fi
    sleep "$sleep_seconds"
    waited=$((waited + sleep_seconds))
  done

  echo "[e2e] timed out waiting for pods with selector ${selector} in namespace ${namespace}" >&2
  kubectl get pods -n "$namespace" -l "$selector" || true
  exit 1
}

resolve_deployment_image() {
  local deployment_name="$1"
  local fallback_image="$2"
  local image

  image="$(kubectl get deployment "$deployment_name" -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || true)"
  if [[ -n "$image" ]]; then
    printf '%s\n' "$image"
    return
  fi
  printf '%s\n' "$fallback_image"
}

create_job_from_stdin() {
  local namespace="$1"
  local job_name="$2"

  kubectl delete job -n "$namespace" "$job_name" --ignore-not-found >/dev/null 2>&1 || true
  kubectl create -f -
}

wait_for_job_completion() {
  local namespace="$1"
  local job_name="$2"
  local timeout="$3"

  if ! kubectl wait -n "$namespace" --for=condition=complete "job/${job_name}" --timeout="$timeout"; then
    echo "[e2e] job ${job_name} failed or timed out" >&2
    kubectl describe job -n "$namespace" "$job_name" || true
    kubectl logs -n "$namespace" "job/${job_name}" --all-containers=true || true
    exit 1
  fi
  kubectl delete job -n "$namespace" "$job_name" --ignore-not-found >/dev/null 2>&1 || true
}

launch_minio_bucket_init() {
  local job_name="${RELEASE_NAME}-minio-bucket-init"

  cat <<EOF_JOB | create_job_from_stdin "${PLATFORM_DATA_NAMESPACE}" "$job_name"
apiVersion: batch/v1
kind: Job
metadata:
  name: ${job_name}
  namespace: ${PLATFORM_DATA_NAMESPACE}
spec:
  ttlSecondsAfterFinished: 3600
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: mc
          image: ${MINIO_BUCKET_INIT_IMAGE}
          command:
            - /bin/sh
            - /config/init-buckets.sh
          env:
            - name: MINIO_ROOT_USER
              valueFrom:
                secretKeyRef:
                  name: minio-root-credentials
                  key: MINIO_ROOT_USER
            - name: MINIO_ROOT_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: minio-root-credentials
                  key: MINIO_ROOT_PASSWORD
            - name: PLATFORM_ACCESS_KEY
              valueFrom:
                secretKeyRef:
                  name: minio-platform-credentials
                  key: MINIO_ACCESS_KEY
            - name: PLATFORM_SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: minio-platform-credentials
                  key: MINIO_SECRET_KEY
            - name: SIMULATION_ACCESS_KEY
              valueFrom:
                secretKeyRef:
                  name: minio-simulation-credentials
                  key: MINIO_ACCESS_KEY
            - name: SIMULATION_SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: minio-simulation-credentials
                  key: MINIO_SECRET_KEY
          volumeMounts:
            - name: config
              mountPath: /config
      volumes:
        - name: config
          configMap:
            name: musematic-minio-bucket-init
            defaultMode: 0755
EOF_JOB
}

launch_clickhouse_schema_init() {
  local job_name="${RELEASE_NAME}-clickhouse-schema-init"

  cat <<EOF_JOB | create_job_from_stdin "${CLICKHOUSE_NAMESPACE}" "$job_name"
apiVersion: batch/v1
kind: Job
metadata:
  name: ${job_name}
  namespace: ${CLICKHOUSE_NAMESPACE}
spec:
  ttlSecondsAfterFinished: 3600
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      initContainers:
        - name: wait-for-clickhouse
          image: ${CLICKHOUSE_SCHEMA_IMAGE}
          env:
            - name: CLICKHOUSE_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: clickhouse-credentials
                  key: CLICKHOUSE_PASSWORD
          command:
            - /bin/bash
            - -ec
            - |
              for attempt in \$(seq 1 60); do
                if clickhouse-client \
                  --host musematic-clickhouse.${CLICKHOUSE_NAMESPACE}.svc.cluster.local \
                  --port 9000 \
                  --user default \
                  --password "\$CLICKHOUSE_PASSWORD" \
                  --query "SELECT 1" >/dev/null 2>&1; then
                  exit 0
                fi
                sleep 5
              done
              exit 1
      containers:
        - name: schema-init
          image: ${CLICKHOUSE_SCHEMA_IMAGE}
          command:
            - /bin/bash
            - -ec
            - |
              cat /scripts/*.sql | clickhouse-client \
                --host musematic-clickhouse.${CLICKHOUSE_NAMESPACE}.svc.cluster.local \
                --port 9000 \
                --user default \
                --password "\$CLICKHOUSE_PASSWORD" \
                --multiquery
          env:
            - name: CLICKHOUSE_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: clickhouse-credentials
                  key: CLICKHOUSE_PASSWORD
          volumeMounts:
            - name: init-scripts
              mountPath: /scripts
      volumes:
        - name: init-scripts
          configMap:
            name: musematic-clickhouse-init
EOF_JOB
}

launch_neo4j_schema_init() {
  local job_name="${RELEASE_NAME}-neo4j-schema-init"

  cat <<EOF_JOB | create_job_from_stdin "${NEO4J_NAMESPACE}" "$job_name"
apiVersion: batch/v1
kind: Job
metadata:
  name: ${job_name}
  namespace: ${NEO4J_NAMESPACE}
spec:
  ttlSecondsAfterFinished: 3600
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      initContainers:
        - name: wait-for-neo4j
          image: ${NEO4J_SCHEMA_IMAGE}
          command:
            - /bin/bash
            - -ec
            - |
              for attempt in \$(seq 1 60); do
                if cypher-shell -u neo4j -p "\$NEO4J_PASSWORD" -a bolt://musematic-neo4j.${NEO4J_NAMESPACE}.svc.cluster.local:7687 "RETURN 1;" >/dev/null 2>&1; then
                  exit 0
                fi
                sleep 5
              done
              exit 1
          env:
            - name: NEO4J_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: neo4j-credentials
                  key: NEO4J_PASSWORD
      containers:
        - name: schema-init
          image: ${NEO4J_SCHEMA_IMAGE}
          command:
            - /bin/bash
            - -ec
            - |
              cypher-shell -u neo4j -p "\$NEO4J_PASSWORD" \
                -a bolt://musematic-neo4j.${NEO4J_NAMESPACE}.svc.cluster.local:7687 \
                -f /scripts/init.cypher
          env:
            - name: NEO4J_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: neo4j-credentials
                  key: NEO4J_PASSWORD
          volumeMounts:
            - name: init-cypher
              mountPath: /scripts
      volumes:
        - name: init-cypher
          configMap:
            name: neo4j-init-cypher
EOF_JOB
}

launch_control_plane_migration() {
  local job_name="${RELEASE_NAME}-control-plane-manual-migrate"
  local image

  image="$(resolve_deployment_image "${RELEASE_NAME}-control-plane-api" "${CONTROL_PLANE_MIGRATION_IMAGE}")"

  cat <<EOF_JOB | create_job_from_stdin "${NAMESPACE}" "$job_name"
apiVersion: batch/v1
kind: Job
metadata:
  name: ${job_name}
  namespace: ${NAMESPACE}
spec:
  ttlSecondsAfterFinished: 3600
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: migrate
          image: ${image}
          imagePullPolicy: IfNotPresent
          command:
            - /bin/sh
            - -ec
            - |
              attempts=${MIGRATION_RETRY_ATTEMPTS}
              delay=${MIGRATION_RETRY_DELAY_SECONDS}
              count=1
              until alembic -c migrations/alembic.ini upgrade head; do
                if [ "\$count" -ge "\$attempts" ]; then
                  echo "migration failed after \$count attempt(s)" >&2
                  exit 1
                fi
                echo "migration attempt \$count/\$attempts failed; retrying in \${delay}s" >&2
                count=\$((count + 1))
                sleep "\$delay"
              done
          env:
            - name: QDRANT_API_KEY
              valueFrom:
                secretKeyRef:
                  name: qdrant-api-key
                  key: QDRANT_API_KEY
                  optional: true
            - name: NEO4J_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: neo4j-credentials
                  key: NEO4J_PASSWORD
                  optional: true
            - name: CLICKHOUSE_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: clickhouse-credentials
                  key: CLICKHOUSE_PASSWORD
                  optional: true
            - name: OPENSEARCH_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: opensearch-credentials
                  key: OPENSEARCH_PASSWORD
                  optional: true
          envFrom:
            - configMapRef:
                name: ${RELEASE_NAME}-control-plane-config
            - secretRef:
                name: ${RELEASE_NAME}-control-plane-secrets
EOF_JOB
}

restart_platform_deployments() {
  echo "[e2e] restarting platform deployments after manual init jobs"
  mapfile -t deployments < <(kubectl get deployments -n "${NAMESPACE}" -o name 2>/dev/null || true)
  for deployment in "${deployments[@]}"; do
    kubectl rollout restart -n "${NAMESPACE}" "$deployment"
  done
}

wait_for_active_pods() {
  local namespace="$1"
  local timeout="$2"
  local timeout_seconds
  local deadline
  local pod

  mapfile -t pods < <(
    kubectl get pods -n "$namespace" \
      --field-selector=status.phase!=Succeeded \
      -l '!cnpg.io/jobRole' \
      -o name 2>/dev/null || true
  )
  if [[ "${#pods[@]}" -eq 0 ]]; then
    return
  fi

  timeout_seconds="$(timeout_to_seconds "$timeout")"
  for pod in "${pods[@]}"; do
    deadline=$(( $(date +%s) + timeout_seconds ))
    while ! pod_ready_or_succeeded "$namespace" "$pod"; do
      if (( $(date +%s) >= deadline )); then
        kubectl wait -n "$namespace" --for=condition=Ready "$pod" --timeout=0s
      fi
      sleep 5
    done
  done
}

timeout_to_seconds() {
  local timeout="$1"

  case "$timeout" in
    *m) echo "$(( ${timeout%m} * 60 ))" ;;
    *s) echo "${timeout%s}" ;;
    *) echo "$timeout" ;;
  esac
}

pod_ready_or_succeeded() {
  local namespace="$1"
  local pod="$2"
  local phase
  local ready

  phase="$(kubectl get -n "$namespace" "$pod" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  if [[ -z "$phase" || "$phase" == "Succeeded" ]]; then
    return 0
  fi

  ready="$(kubectl get -n "$namespace" "$pod" -o jsonpath='{range .status.conditions[?(@.type=="Ready")]}{.status}{end}' 2>/dev/null || true)"
  [[ "$ready" == "True" ]]
}

wait_for_deployment_rollouts() {
  local namespace="$1"
  local timeout="$2"
  mapfile -t deployments < <(kubectl get deployments -n "$namespace" -o name 2>/dev/null || true)
  for deployment in "${deployments[@]}"; do
    kubectl rollout status -n "$namespace" "$deployment" --timeout="$timeout"
  done
}

wait_for_kafka_ready() {
  if ! kubectl get kafka -n "${KAFKA_NAMESPACE}" "${KAFKA_CLUSTER_NAME}" >/dev/null 2>&1; then
    return
  fi
  if kubectl wait --for=condition=Ready -n "${KAFKA_NAMESPACE}" "kafka/${KAFKA_CLUSTER_NAME}" --timeout="${PLATFORM_READY_TIMEOUT}"; then
    return
  fi

  echo "[e2e] Kafka cluster ${KAFKA_CLUSTER_NAME} did not become Ready in ${KAFKA_NAMESPACE}" >&2
  kubectl get kafka -n "${KAFKA_NAMESPACE}" "${KAFKA_CLUSTER_NAME}" -o yaml >&2 || true
  kubectl get pods -n "${KAFKA_NAMESPACE}" -l "strimzi.io/cluster=${KAFKA_CLUSTER_NAME}" -o wide >&2 || true
  kubectl describe pods -n "${KAFKA_NAMESPACE}" -l "strimzi.io/cluster=${KAFKA_CLUSTER_NAME}" >&2 || true
  exit 1
}

wait_for_kafka_topics_ready() {
  local timeout="$1"
  local selector="strimzi.io/cluster=${KAFKA_CLUSTER_NAME}"

  if ! kubectl get kafkatopic -n "${KAFKA_NAMESPACE}" -l "$selector" >/dev/null 2>&1; then
    return
  fi

  kubectl wait --for=condition=Ready -n "${KAFKA_NAMESPACE}" kafkatopic -l "$selector" --timeout="$timeout"
}

redis_cluster_pods() {
  kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name=redis-cluster \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | sort
}

wait_for_redis_processes() {
  local pod
  local attempt
  local ready
  local redis_pods=("$@")

  for pod in "${redis_pods[@]}"; do
    ready=false
    for attempt in $(seq 1 120); do
      if kubectl exec -n "${NAMESPACE}" "$pod" -- bash -ec '
        REDISCLI_AUTH="$(cat "$REDIS_PASSWORD_FILE")"
        export REDISCLI_AUTH
        redis-cli -h 127.0.0.1 -p "${REDIS_PORT_NUMBER:-6379}" ping
      ' >/dev/null 2>&1; then
        ready=true
        break
      fi
      sleep 5
    done
    if [[ "$ready" != "true" ]]; then
      echo "[e2e] Redis process in ${pod} did not accept PING before timeout" >&2
      return 1
    fi
  done
}

redis_cluster_state() {
  kubectl exec -n "${NAMESPACE}" musematic-redis-0 -- bash -ec '
    REDISCLI_AUTH="$(cat "$REDIS_PASSWORD_FILE")"
    export REDISCLI_AUTH
    redis-cli -h 127.0.0.1 -p "${REDIS_PORT_NUMBER:-6379}" cluster info \
      | sed -n "s/^cluster_state://p" \
      | tr -d "\r"
  ' 2>/dev/null || true
}

redis_cluster_node_targets() {
  local pod
  for pod in "$@"; do
    printf '%s.musematic-redis-headless.%s.svc.cluster.local:6379\n' "$pod" "${NAMESPACE}"
  done
}

reset_redis_cluster_nodes() {
  local pod
  for pod in "$@"; do
    kubectl exec -n "${NAMESPACE}" "$pod" -- bash -ec '
      REDISCLI_AUTH="$(cat "$REDIS_PASSWORD_FILE")"
      export REDISCLI_AUTH
      redis-cli -h 127.0.0.1 -p "${REDIS_PORT_NUMBER:-6379}" cluster reset hard >/dev/null 2>&1 || true
    '
  done
}

create_redis_cluster() {
  local bootstrap_pod="$1"
  shift

  kubectl exec -n "${NAMESPACE}" "$bootstrap_pod" -- bash -ec '
    REDISCLI_AUTH="$(cat "$REDIS_PASSWORD_FILE")"
    export REDISCLI_AUTH
    redis-cli --cluster create "$@" --cluster-replicas 0 --cluster-yes
  ' redis-cluster-create "$@"
}

ensure_redis_cluster_initialized() {
  local attempt
  local state
  local -a redis_pods
  local -a node_targets

  mapfile -t redis_pods < <(redis_cluster_pods)
  if [[ "${#redis_pods[@]}" -eq 0 ]]; then
    echo "[e2e] Redis StatefulSet exists but no redis-cluster pods were found" >&2
    exit 1
  fi

  wait_for_redis_processes "${redis_pods[@]}"

  state="$(redis_cluster_state)"
  if [[ "$state" == "ok" ]]; then
    return
  fi

  echo "[e2e] Redis cluster state is ${state:-unknown}; recreating e2e cluster topology"
  reset_redis_cluster_nodes "${redis_pods[@]}"
  mapfile -t node_targets < <(redis_cluster_node_targets "${redis_pods[@]}")
  create_redis_cluster "${redis_pods[0]}" "${node_targets[@]}"

  for attempt in $(seq 1 60); do
    state="$(redis_cluster_state)"
    if [[ "$state" == "ok" ]]; then
      return
    fi
    sleep 5
  done

  echo "[e2e] Redis cluster did not reach cluster_state:ok after manual initialization" >&2
  kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name=redis-cluster -o wide >&2 || true
  kubectl describe pods -n "${NAMESPACE}" -l app.kubernetes.io/name=redis-cluster >&2 || true
  kubectl logs -n "${NAMESPACE}" -l app.kubernetes.io/name=redis-cluster --tail=200 >&2 || true
  exit 1
}

wait_for_redis_ready() {
  if ! kubectl get statefulset -n "${NAMESPACE}" musematic-redis >/dev/null 2>&1; then
    return
  fi

  echo "[e2e] waiting for Redis cluster before restarting platform deployments"
  ensure_redis_cluster_initialized
  kubectl wait --for=condition=Ready -n "${NAMESPACE}" pod -l app.kubernetes.io/name=redis-cluster --timeout="${PLATFORM_READY_TIMEOUT}"
  kubectl rollout status -n "${NAMESPACE}" statefulset/musematic-redis --timeout="${PLATFORM_READY_TIMEOUT}"
}

run_manual_init_jobs() {
  echo "[e2e] launching manual init jobs outside Helm hooks"
  launch_minio_bucket_init
  if kubectl get statefulset -n "${CLICKHOUSE_NAMESPACE}" musematic-clickhouse >/dev/null 2>&1; then
    launch_clickhouse_schema_init
  fi
  if kubectl get statefulset -n "${NEO4J_NAMESPACE}" musematic-neo4j >/dev/null 2>&1; then
    launch_neo4j_schema_init
  fi
  wait_for_labelled_pod "${PLATFORM_DATA_NAMESPACE}" "cnpg.io/cluster=musematic-postgres,cnpg.io/podRole=instance" "${POSTGRES_READY_TIMEOUT}"
  launch_control_plane_migration

  wait_for_job_completion "${PLATFORM_DATA_NAMESPACE}" "${RELEASE_NAME}-minio-bucket-init" "${JOB_READY_TIMEOUT}"
  if kubectl get job -n "${CLICKHOUSE_NAMESPACE}" "${RELEASE_NAME}-clickhouse-schema-init" >/dev/null 2>&1; then
    wait_for_job_completion "${CLICKHOUSE_NAMESPACE}" "${RELEASE_NAME}-clickhouse-schema-init" "${JOB_READY_TIMEOUT}"
  fi
  if kubectl get job -n "${NEO4J_NAMESPACE}" "${RELEASE_NAME}-neo4j-schema-init" >/dev/null 2>&1; then
    wait_for_job_completion "${NEO4J_NAMESPACE}" "${RELEASE_NAME}-neo4j-schema-init" "${JOB_READY_TIMEOUT}"
  fi
  wait_for_job_completion "${NAMESPACE}" "${RELEASE_NAME}-control-plane-manual-migrate" "${JOB_READY_TIMEOUT}"
}

wait_for_rollouts() {
  wait_for_active_pods "${PLATFORM_DATA_NAMESPACE}" "${PLATFORM_READY_TIMEOUT}"
  wait_for_deployment_rollouts "${NAMESPACE}" "${PLATFORM_READY_TIMEOUT}"
  wait_for_active_pods "${NAMESPACE}" "${PLATFORM_READY_TIMEOUT}"
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
  ensure_supporting_namespaces
  install_cnpg_operator
  install_strimzi_operator
  adopt_existing_kafka_topics
  if [[ "${SKIP_LOAD_IMAGES}" != "true" ]]; then
    "${CLUSTER_DIR}/load-images.sh"
  fi
  install_observability
  install_platform
  install_vault
  run_manual_init_jobs
  wait_for_kafka_ready
  wait_for_kafka_topics_ready "${PLATFORM_READY_TIMEOUT}"
  wait_for_redis_ready
  restart_platform_deployments
  wait_for_rollouts
  seed_baseline
  cat <<EOF_SUMMARY
[e2e] environment ready
  UI:  http://localhost:${PORT_UI}
  API: http://localhost:${PORT_API}
  WS:  ws://localhost:${PORT_WS}
  Vault: http://localhost:${PORT_VAULT}
EOF_SUMMARY
}

main "$@"
