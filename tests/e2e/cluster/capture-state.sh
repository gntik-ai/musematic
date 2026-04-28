#!/usr/bin/env bash
set -euo pipefail

RELEASE_NAME="${RELEASE_NAME:-amp}"
NAMESPACES=(platform platform-execution platform-data platform-observability strimzi-system)

section() {
  printf '\n===== %s =====\n' "$1"
}

section "kind clusters"
kind get clusters || true

section "kubectl get pods -A"
kubectl get pods -A || true

section "kubectl get jobs -A"
kubectl get jobs -A || true

section "kubectl describe jobs -A"
kubectl describe jobs -A || true

section "kubectl get pvc -A"
kubectl get pvc -A || true

section "kubectl get events -A"
kubectl get events -A --sort-by=.metadata.creationTimestamp || true

section "helm list -A"
helm list -A || true

for namespace in "${NAMESPACES[@]}"; do
  section "helm status ${RELEASE_NAME} in ${namespace}"
  helm status "${RELEASE_NAME}" -n "${namespace}" || true

  section "pods in ${namespace}"
  kubectl get pods -n "${namespace}" || true

  mapfile -t pods < <(kubectl get pods -n "${namespace}" -o name 2>/dev/null || true)
  for pod in "${pods[@]}"; do
    section "describe ${pod} (${namespace})"
    kubectl describe -n "${namespace}" "${pod}" || true

    section "logs ${pod} (${namespace})"
    kubectl logs -n "${namespace}" "${pod#pod/}" --tail=100 || true
  done
done
