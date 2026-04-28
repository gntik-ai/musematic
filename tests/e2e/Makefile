CLUSTER_NAME ?= amp-e2e
PORT_UI ?= 8080
PORT_API ?= 8081
PORT_WS ?= 8082
PORT_GOOGLE_OIDC ?= 8083
PORT_GITHUB_OAUTH ?= 8084
RELEASE_NAME ?= amp
NAMESPACE ?= platform

PYTEST ?= python3 -m pytest
E2E_TEST_PATHS ?= suites tests test_*.py
E2E_JOURNEY_WORKERS ?= 4
KIND_CONFIG_TEMPLATE := cluster/kind-config.yaml
KIND_CONFIG_RENDERED := /tmp/kind-config-$(CLUSTER_NAME).yaml

export PLATFORM_API_URL ?= http://localhost:$(PORT_API)
export PLATFORM_WS_URL ?= ws://localhost:$(PORT_WS)
export MOCK_GOOGLE_OIDC_URL ?= http://localhost:$(PORT_GOOGLE_OIDC)
export MOCK_GITHUB_OAUTH_URL ?= http://localhost:$(PORT_GITHUB_OAUTH)

.PHONY: e2e-check render-kind-config load-images e2e-up e2e-down e2e-test e2e-chaos e2e-perf e2e-reset e2e-logs e2e-shell capture-state e2e-journeys e2e-j01 e2e-j02 e2e-j03 e2e-j04 e2e-j05 e2e-j06 e2e-j07 e2e-j08 e2e-j09

e2e-check:
	@command -v docker >/dev/null 2>&1 || (echo "docker is required" >&2; exit 1)
	@command -v kind >/dev/null 2>&1 || (echo "kind is required" >&2; exit 1)
	@command -v kubectl >/dev/null 2>&1 || (echo "kubectl is required" >&2; exit 1)
	@command -v helm >/dev/null 2>&1 || (echo "helm is required" >&2; exit 1)
	@command -v python3 >/dev/null 2>&1 || (echo "python3 is required" >&2; exit 1)
	@command -v envsubst >/dev/null 2>&1 || (echo "envsubst is required" >&2; exit 1)

render-kind-config:
	@CLUSTER_NAME=$(CLUSTER_NAME) PORT_UI=$(PORT_UI) PORT_API=$(PORT_API) PORT_WS=$(PORT_WS) PORT_GOOGLE_OIDC=$(PORT_GOOGLE_OIDC) PORT_GITHUB_OAUTH=$(PORT_GITHUB_OAUTH) envsubst < $(KIND_CONFIG_TEMPLATE) > $(KIND_CONFIG_RENDERED)

load-images:
	@CLUSTER_NAME=$(CLUSTER_NAME) ./cluster/load-images.sh

e2e-up: render-kind-config
	@CLUSTER_NAME=$(CLUSTER_NAME) PORT_UI=$(PORT_UI) PORT_API=$(PORT_API) PORT_WS=$(PORT_WS) PORT_GOOGLE_OIDC=$(PORT_GOOGLE_OIDC) PORT_GITHUB_OAUTH=$(PORT_GITHUB_OAUTH) RELEASE_NAME=$(RELEASE_NAME) NAMESPACE=$(NAMESPACE) KIND_CONFIG_PATH=$(KIND_CONFIG_RENDERED) ./cluster/install.sh

e2e-down:
	@kind delete cluster --name $(CLUSTER_NAME)
	@rm -f $(KIND_CONFIG_RENDERED)

e2e-test:
	@mkdir -p reports
	@$(PYTEST) $(E2E_TEST_PATHS) --junitxml=reports/junit.xml --html=reports/report.html --self-contained-html

e2e-journeys:
	@mkdir -p reports
	@$(PYTEST) journeys/ -n $(E2E_JOURNEY_WORKERS) --dist=loadfile -v -m journey --junitxml=reports/journeys-junit.xml --html=reports/journeys-report.html

e2e-j01:
	@mkdir -p reports
	@$(PYTEST) journeys/ -v -m j01_admin --junitxml=reports/j01-junit.xml --html=reports/j01-report.html

e2e-j02:
	@mkdir -p reports
	@$(PYTEST) journeys/ -v -m j02_creator --junitxml=reports/j02-junit.xml --html=reports/j02-report.html

e2e-j03:
	@mkdir -p reports
	@$(PYTEST) journeys/ -v -m j03_consumer --junitxml=reports/j03-junit.xml --html=reports/j03-report.html

e2e-j04:
	@mkdir -p reports
	@$(PYTEST) journeys/ -v -m j04_workspace_goal --junitxml=reports/j04-junit.xml --html=reports/j04-report.html

e2e-j05:
	@mkdir -p reports
	@$(PYTEST) journeys/ -v -m j05_trust --junitxml=reports/j05-junit.xml --html=reports/j05-report.html

e2e-j06:
	@mkdir -p reports
	@$(PYTEST) journeys/ -v -m j06_operator --junitxml=reports/j06-junit.xml --html=reports/j06-report.html

e2e-j07:
	@mkdir -p reports
	@$(PYTEST) journeys/ -v -m j07_evaluator --junitxml=reports/j07-junit.xml --html=reports/j07-report.html

e2e-j08:
	@mkdir -p reports
	@$(PYTEST) journeys/ -v -m j08_external --junitxml=reports/j08-junit.xml --html=reports/j08-report.html

e2e-j09:
	@mkdir -p reports
	@$(PYTEST) journeys/ -v -m j09_discovery --junitxml=reports/j09-junit.xml --html=reports/j09-report.html

e2e-chaos:
	@if [ -d chaos ] && find chaos -type f \( -name 'test_*.py' -o -name '*_test.py' \) | grep -q .; then \
		mkdir -p reports; \
		$(PYTEST) chaos --junitxml=reports/chaos-junit.xml --html=reports/chaos-report.html --self-contained-html; \
	else \
		echo "[e2e] no chaos suites found; skipping"; \
	fi

e2e-perf:
	@if [ -d performance ] && find performance -type f \( -name 'test_*.py' -o -name '*_test.py' \) | grep -q .; then \
		mkdir -p reports; \
		$(PYTEST) performance --junitxml=reports/performance-junit.xml --html=reports/performance-report.html --self-contained-html; \
	else \
		echo "[e2e] no performance suites found; skipping"; \
	fi

e2e-reset:
	@python3 -m seeders.base --all --reset

e2e-logs:
	@kubectl get pods -A

e2e-shell:
	@kubectl -n $(NAMESPACE) exec -it deployment/$(RELEASE_NAME)-control-plane-api -- /bin/sh

capture-state:
	@RELEASE_NAME=$(RELEASE_NAME) ./cluster/capture-state.sh
