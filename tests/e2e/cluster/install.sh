#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CLUSTER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-amp-e2e}"
RELEASE_NAME="${RELEASE_NAME:-amp}"
NAMESPACE="${NAMESPACE:-platform}"
PLATFORM_DATA_NAMESPACE="${PLATFORM_DATA_NAMESPACE:-platform-data}"
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
PLATFORM_READY_TIMEOUT="${PLATFORM_READY_TIMEOUT:-600s}"
POSTGRES_READY_TIMEOUT="${POSTGRES_READY_TIMEOUT:-600s}"
JOB_READY_TIMEOUT="${JOB_READY_TIMEOUT:-600s}"
MIGRATION_RETRY_ATTEMPTS="${MIGRATION_RETRY_ATTEMPTS:-60}"
MIGRATION_RETRY_DELAY_SECONDS="${MIGRATION_RETRY_DELAY_SECONDS:-5}"
CONTROL_PLANE_MIGRATION_IMAGE="${CONTROL_PLANE_MIGRATION_IMAGE:-ghcr.io/musematic/control-plane:local}"
CLICKHOUSE_SCHEMA_IMAGE="${CLICKHOUSE_SCHEMA_IMAGE:-clickhouse/clickhouse-server:24.3}"
NEO4J_SCHEMA_IMAGE="${NEO4J_SCHEMA_IMAGE:-neo4j:5.21.2-enterprise}"
MINIO_BUCKET_INIT_IMAGE="${MINIO_BUCKET_INIT_IMAGE:-minio/mc:latest}"

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
  ttlSecondsAfterFinished: 300
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

  cat <<EOF_JOB | create_job_from_stdin "${PLATFORM_DATA_NAMESPACE}" "$job_name"
apiVersion: batch/v1
kind: Job
metadata:
  name: ${job_name}
  namespace: ${PLATFORM_DATA_NAMESPACE}
spec:
  ttlSecondsAfterFinished: 300
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      initContainers:
        - name: wait-for-clickhouse
          image: ${CLICKHOUSE_SCHEMA_IMAGE}
          command:
            - /bin/bash
            - -ec
            - |
              for attempt in $(seq 1 60); do
                if curl -fsS http://musematic-clickhouse.${PLATFORM_DATA_NAMESPACE}.svc.cluster.local:8123/ping >/dev/null; then
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
                --host musematic-clickhouse.${PLATFORM_DATA_NAMESPACE}.svc.cluster.local \
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

  cat <<EOF_JOB | create_job_from_stdin "${PLATFORM_DATA_NAMESPACE}" "$job_name"
apiVersion: batch/v1
kind: Job
metadata:
  name: ${job_name}
  namespace: ${PLATFORM_DATA_NAMESPACE}
spec:
  ttlSecondsAfterFinished: 300
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
              for attempt in $(seq 1 60); do
                if cypher-shell -u neo4j -p "\$NEO4J_PASSWORD" -a bolt://musematic-neo4j.${PLATFORM_DATA_NAMESPACE}.svc.cluster.local:7687 "RETURN 1;" >/dev/null 2>&1; then
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
                -a bolt://musematic-neo4j.${PLATFORM_DATA_NAMESPACE}.svc.cluster.local:7687 \
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
  ttlSecondsAfterFinished: 300
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
  mapfile -t pods < <(kubectl get pods -n "$namespace" --field-selector=status.phase!=Succeeded -o name 2>/dev/null || true)
  if [[ "${#pods[@]}" -eq 0 ]]; then
    return
  fi
  kubectl wait -n "$namespace" --for=condition=Ready "${pods[@]}" --timeout="$timeout"
}

wait_for_deployment_rollouts() {
  local namespace="$1"
  local timeout="$2"
  mapfile -t deployments < <(kubectl get deployments -n "$namespace" -o name 2>/dev/null || true)
  for deployment in "${deployments[@]}"; do
    kubectl rollout status -n "$namespace" "$deployment" --timeout="$timeout"
  done
}

run_manual_init_jobs() {
  echo "[e2e] launching manual init jobs outside Helm hooks"
  launch_minio_bucket_init
  launch_clickhouse_schema_init
  launch_neo4j_schema_init
  wait_for_labelled_pod "${PLATFORM_DATA_NAMESPACE}" "cnpg.io/cluster=musematic-postgres" "${POSTGRES_READY_TIMEOUT}"
  launch_control_plane_migration

  wait_for_job_completion "${PLATFORM_DATA_NAMESPACE}" "${RELEASE_NAME}-minio-bucket-init" "${JOB_READY_TIMEOUT}"
  wait_for_job_completion "${PLATFORM_DATA_NAMESPACE}" "${RELEASE_NAME}-clickhouse-schema-init" "${JOB_READY_TIMEOUT}"
  wait_for_job_completion "${PLATFORM_DATA_NAMESPACE}" "${RELEASE_NAME}-neo4j-schema-init" "${JOB_READY_TIMEOUT}"
  wait_for_job_completion "${NAMESPACE}" "${RELEASE_NAME}-control-plane-manual-migrate" "${JOB_READY_TIMEOUT}"
}

wait_for_rollouts() {
  wait_for_active_pods "${PLATFORM_DATA_NAMESPACE}" "${PLATFORM_READY_TIMEOUT}"
  wait_for_active_pods "${NAMESPACE}" "${PLATFORM_READY_TIMEOUT}"
  wait_for_deployment_rollouts "${NAMESPACE}" "${PLATFORM_READY_TIMEOUT}"
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
  run_manual_init_jobs
  restart_platform_deployments
  wait_for_rollouts
  seed_baseline
  cat <<EOF_SUMMARY
[e2e] environment ready
  UI:  http://localhost:${PORT_UI}
  API: http://localhost:${PORT_API}
  WS:  ws://localhost:${PORT_WS}
EOF_SUMMARY
}

main "$@"
