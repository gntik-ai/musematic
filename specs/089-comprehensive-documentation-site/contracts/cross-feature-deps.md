# Cross-Feature Dependencies for UPD-039

Verified on 2026-04-27 from the feature directories and current working tree.

## Feature 086: Administrator Workbench

`specs/086-administrator-workbench-and/` exists and includes planning artifacts plus
contracts for the admin page inventory and per-bounded-context admin routers.

The corresponding frontend and backend code is present in the current tree:

- `apps/web/e2e/admin-*.spec.ts` and `apps/web/e2e/admin/`
- `apps/control-plane/migrations/versions/067_admin_workbench.py`
- Admin workbench references in `apps/web/lib/hooks/use-admin-settings.ts`

UPD-039 can author Administrator Guide pages against the feature 086 route and page
inventory. If any page named in the spec is still incomplete, the guide page should
ship with an explicit TODO marker and the related FR number.

## Feature 087: Public Signup Flow

`specs/087-public-signup-flow/` exists and includes contracts for email
localization and rate-limit policies.

The current tree includes signup and OAuth E2E coverage in:

- `apps/web/e2e/admin-signup.spec.ts`
- `apps/web/e2e/auth/login.spec.ts`
- `apps/control-plane/src/platform/auth/router_oauth.py`

UPD-039 can author User Guide signup and OAuth pages against the feature 087
contracts. If a referenced route is not implemented when authoring begins, the page
should retain a TODO marker and cite the feature 087 contract path.

## Sequencing Decision

Track B content should prefer real route names and API references from features 086
and 087. Placeholder pages are acceptable only when the implementation artifact is
absent or still behind its own feature branch.
