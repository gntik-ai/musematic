CLUSTER_NAME ?= amp-e2e
PORT_UI ?= 8080
PORT_API ?= 8081
PORT_WS ?= 8082
RELEASE_NAME ?= amp
NAMESPACE ?= platform

PYTEST ?= python3 -m pytest
KIND_CONFIG_TEMPLATE := cluster/kind-config.yaml
KIND_CONFIG_RENDERED := /tmp/kind-config-$(CLUSTER_NAME).yaml

export PLATFORM_API_URL ?= http://localhost:$(PORT_API)
export PLATFORM_WS_URL ?= ws://localhost:$(PORT_WS)

.PHONY: e2e-check render-kind-config e2e-up e2e-down e2e-test e2e-chaos e2e-perf e2e-reset e2e-logs e2e-shell capture-state

e2e-check:
	@command -v docker >/dev/null 2>&1 || (echo "docker is required" >&2; exit 1)
	@command -v kind >/dev/null 2>&1 || (echo "kind is required" >&2; exit 1)
	@command -v kubectl >/dev/null 2>&1 || (echo "kubectl is required" >&2; exit 1)
	@command -v helm >/dev/null 2>&1 || (echo "helm is required" >&2; exit 1)
	@command -v python3 >/dev/null 2>&1 || (echo "python3 is required" >&2; exit 1)
	@command -v envsubst >/dev/null 2>&1 || (echo "envsubst is required" >&2; exit 1)

render-kind-config:
	@CLUSTER_NAME=$(CLUSTER_NAME) PORT_UI=$(PORT_UI) PORT_API=$(PORT_API) PORT_WS=$(PORT_WS) envsubst < $(KIND_CONFIG_TEMPLATE) > $(KIND_CONFIG_RENDERED)

e2e-up: render-kind-config
	@CLUSTER_NAME=$(CLUSTER_NAME) PORT_UI=$(PORT_UI) PORT_API=$(PORT_API) PORT_WS=$(PORT_WS) RELEASE_NAME=$(RELEASE_NAME) NAMESPACE=$(NAMESPACE) KIND_CONFIG_PATH=$(KIND_CONFIG_RENDERED) ./cluster/install.sh

e2e-down:
	@kind delete cluster --name $(CLUSTER_NAME)
	@rm -f $(KIND_CONFIG_RENDERED)

e2e-test:
	@$(PYTEST) suites

e2e-chaos:
	@$(PYTEST) chaos

e2e-perf:
	@$(PYTEST) performance

e2e-reset:
	@python3 -m seeders.base --all --reset

e2e-logs:
	@kubectl get pods -A

e2e-shell:
	@kubectl -n $(NAMESPACE) exec -it deployment/$(RELEASE_NAME)-control-plane-api -- /bin/sh

capture-state:
	@RELEASE_NAME=$(RELEASE_NAME) ./cluster/capture-state.sh
