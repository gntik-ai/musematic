NAME ?= new_migration

.PHONY: migrate migrate-rollback migrate-create migrate-check

migrate:
	cd apps/control-plane && alembic -c migrations/alembic.ini upgrade head

migrate-rollback:
	cd apps/control-plane && alembic -c migrations/alembic.ini downgrade -1

migrate-create:
	cd apps/control-plane && alembic -c migrations/alembic.ini revision --autogenerate -m "$(NAME)"

migrate-check:
	cd apps/control-plane && alembic -c migrations/alembic.ini branches --verbose

