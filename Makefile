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
