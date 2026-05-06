NAME ?= new_migration

DEV_CLUSTER_NAME ?= amp-e2e
DEV_PORT_UI ?= 8080
DEV_PORT_API ?= 8081
DEV_PORT_WS ?= 8082
DEV_PORT_GOOGLE_OIDC ?= 8083
DEV_PORT_GITHUB_OAUTH ?= 8084

DEV_E2E_ARGS = \
	CLUSTER_NAME=$(DEV_CLUSTER_NAME) \
	PORT_UI=$(DEV_PORT_UI) \
	PORT_API=$(DEV_PORT_API) \
	PORT_WS=$(DEV_PORT_WS) \
	PORT_GOOGLE_OIDC=$(DEV_PORT_GOOGLE_OIDC) \
	PORT_GITHUB_OAUTH=$(DEV_PORT_GITHUB_OAUTH)

.PHONY: migrate migrate-rollback migrate-create migrate-check dev-check dev-load-images dev-up dev-down dev-reset dev-logs dev-shell

migrate:
	cd apps/control-plane && alembic -c migrations/alembic.ini upgrade head

migrate-rollback:
	cd apps/control-plane && alembic -c migrations/alembic.ini downgrade -1

migrate-create:
	cd apps/control-plane && alembic -c migrations/alembic.ini revision --autogenerate -m "$(NAME)"

migrate-check:
	cd apps/control-plane && alembic -c migrations/alembic.ini branches --verbose

dev-check:
	@$(MAKE) -C tests/e2e e2e-check $(DEV_E2E_ARGS)

dev-load-images:
	@$(MAKE) -C tests/e2e load-images $(DEV_E2E_ARGS)

dev-up: dev-check
	@SKIP_LOAD_IMAGES=$(SKIP_LOAD_IMAGES) $(MAKE) -C tests/e2e e2e-up $(DEV_E2E_ARGS)

dev-down:
	@$(MAKE) -C tests/e2e e2e-down $(DEV_E2E_ARGS)

dev-reset:
	@$(MAKE) -C tests/e2e e2e-reset $(DEV_E2E_ARGS)

dev-logs:
	@$(MAKE) -C tests/e2e e2e-logs $(DEV_E2E_ARGS)

dev-shell:
	@$(MAKE) -C tests/e2e e2e-shell $(DEV_E2E_ARGS)

# UPD-053 (106) — regenerate the committed Helm snapshot fixtures the CI snapshot-diff
# gate compares against. Run after any chart template / values change; review the diff
# in `git diff deploy/helm/platform/.snapshots/` and commit both files.
helm-snapshot-update:
	@mkdir -p deploy/helm/platform/.snapshots
	@helm dependency update deploy/helm/platform >/dev/null
	@helm template release deploy/helm/platform -f deploy/helm/platform/values.prod.yaml \
		--kube-version 1.29.0 \
		--api-versions cert-manager.io/v1/Certificate \
		--api-versions cert-manager.io/v1/ClusterIssuer \
		| python3 scripts/normalize-helm-snapshot.py \
		> deploy/helm/platform/.snapshots/prod.rendered.yaml
	@helm template release deploy/helm/platform -f deploy/helm/platform/values.dev.yaml \
		--kube-version 1.29.0 \
		--api-versions cert-manager.io/v1/Certificate \
		--api-versions cert-manager.io/v1/ClusterIssuer \
		| python3 scripts/normalize-helm-snapshot.py \
		> deploy/helm/platform/.snapshots/dev.rendered.yaml
	@echo "Snapshots regenerated. Review with: git diff deploy/helm/platform/.snapshots/"

# UPD-054 (107) — SaaS pass E2E suite convenience targets. Run J22–J37 (the
# new SaaS journeys) against a dev kind cluster brought up via `make e2e-up`.
# Honours E2E_JOURNEY_WORKERS (default 4) and the optional RUN_J29=1 toggle
# for live Hetzner DNS coverage. See specs/107-saas-e2e-journeys/quickstart.md.
e2e-saas-suite:
	@cd tests/e2e && \
		E2E_JOURNEY_WORKERS=$${E2E_JOURNEY_WORKERS:-4} \
		python -m pytest \
		journeys/test_j22_*.py \
		journeys/test_j23_*.py \
		journeys/test_j24_*.py \
		journeys/test_j25_*.py \
		journeys/test_j26_*.py \
		journeys/test_j27_*.py \
		journeys/test_j28_*.py \
		journeys/test_j29_*.py \
		journeys/test_j30_*.py \
		journeys/test_j31_*.py \
		journeys/test_j32_*.py \
		journeys/test_j33_*.py \
		journeys/test_j34_*.py \
		journeys/test_j35_*.py \
		journeys/test_j36_*.py \
		journeys/test_j37_*.py \
		-m journey \
		-n $${E2E_JOURNEY_WORKERS:-4} \
		--timeout=480 \
		--junitxml=reports/saas-pass.xml

# UPD-054 (107) — full SaaS pass acceptance: J01–J21 regression PLUS the new
# J22–J37. The canonical "SaaS pass passes" check.
e2e-saas-acceptance: e2e-saas-suite
	@cd tests/e2e && \
		E2E_JOURNEY_WORKERS=$${E2E_JOURNEY_WORKERS:-4} \
		python -m pytest \
		journeys/test_j01_*.py \
		journeys/test_j02_*.py \
		journeys/test_j03_*.py \
		journeys/test_j04_*.py \
		journeys/test_j05_*.py \
		journeys/test_j06_*.py \
		journeys/test_j07_*.py \
		journeys/test_j08_*.py \
		journeys/test_j09_*.py \
		journeys/test_j10_*.py \
		journeys/test_j11_*.py \
		journeys/test_j12_*.py \
		journeys/test_j13_*.py \
		journeys/test_j14_*.py \
		journeys/test_j15_*.py \
		journeys/test_j16_*.py \
		journeys/test_j17_*.py \
		journeys/test_j18_*.py \
		journeys/test_j19_*.py \
		journeys/test_j20_*.py \
		journeys/test_j21_*.py \
		-m journey \
		-n $${E2E_JOURNEY_WORKERS:-4} \
		--timeout=480 \
		--junitxml=reports/saas-pass-regression.xml

# UPD-054 (107) — soak run for SC-006 orphan-resource verification. Runs
# e2e-saas-suite 100x in a tight loop and exits non-zero if any iteration
# fails OR if verify_no_orphans.py reports leaked test resources at the end.
e2e-saas-soak:
	@iter=$${E2E_SAAS_SOAK_ITERATIONS:-100}; \
	for i in $$(seq 1 $$iter); do \
		echo "=== soak iteration $$i / $$iter ==="; \
		$(MAKE) e2e-saas-suite || exit 1; \
	done
	@python tests/e2e/scripts/verify_no_orphans.py
