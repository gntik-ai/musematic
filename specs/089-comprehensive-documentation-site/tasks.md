# Tasks: UPD-039 — Comprehensive Documentation Site and Installation Guides

**Feature**: 089-comprehensive-documentation-site
**Branch**: `089-comprehensive-documentation-site`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

User stories (from spec.md):
- **US1 (P1)** — Operator installs Musematic on Hetzner end-to-end in ≤ 3 hours via the FR-608 Hetzner installation guide (the flagship production-deployment story)
- **US2 (P1)** — Developer consults the auto-generated API Reference (Redoc + Swagger UI + 4-language code samples + error catalog) per FR-619
- **US3 (P1)** — Super admin consults the auto-generated environment variables reference per FR-610 (CI-enforced no drift)
- **US4 (P2)** — Spanish-speaking user reads the localized User Guide in 6 locales per FR-620 (page-context-preserving language toggle)
- **US5 (P1)** — On-call operator uses the FR-617 runbook library during an incident (≥ 10 runbooks: platform upgrade / DR restore / failover / failback / secret rotation / capacity expansion / break-glass / incident response / LogQL cookbook / TLS emergency renewal)

Independent-test discipline: every US MUST be verifiable in isolation. US1 = end-to-end Hetzner deployment on a fresh account in ≤ 3 hours. US2 = open the API Reference and copy a working code sample. US3 = synthetic PR adding `os.getenv("PLATFORM_NEW_VAR")` without regenerating docs — CI fails with clear drift error. US4 = native-speaker review per locale (≥ 4/5 quality rating per SC-003 pattern from feature 088). US5 = simulated incident → runbook search → resolution.

**Wave-14 sub-division** (per plan.md §"Wave layout"):
- W14.0 — Setup: T001-T004
- W14A — Site infrastructure (Track A): T005-T035
- W14B — User-facing docs (Track B): T046-T060
- W14C — Technical docs (Track C): T073-T085
- W14D — Installation guides + runbooks (Track D): T061-T097
- W14E — Translation: T098-T104
- W14F — Verification + deploy: T105-T110
- W14G — Polish: T111-T117

---

## Phase 1: Setup

- [ ] T001 [W14.0] Verify the on-disk repo state per plan.md correction §3 + §10: confirm `mkdocs.yml` exists at the repo root with Material theme + 16 features + search plugin (verified per inventory at lines 1-137); confirm `requirements-docs.txt` has the 3 baseline deps (`mkdocs==1.6.1`, `mkdocs-material==9.5.45`, `pymdown-extensions==10.12`); confirm the `docs/` tree has 13 .md files + 1 SVG across 7 directories (`administration/`, `development/`, `features/`, `integrations/`, `operations/` + 4 top-level files + `assets/architecture-overview.svg`); confirm NO `terraform/` directory exists; confirm NO `SECURITY.md` exists at the repo root. Document the inventory in `specs/089-comprehensive-documentation-site/contracts/repo-inventory.md` (NEW file).
- [ ] T002 [P] [W14.0] Verify the existing CI substrate per plan.md correction §8: read `.github/workflows/ci.yml`'s `dorny/paths-filter@v3` block at lines 40-79; confirm a `docs:` filter does NOT exist; confirm the existing filters for `python`, `go-*`, `frontend`, `helm`, `migrations`, `proto`, `images`, `readme`. Document the integration plan (where the `docs:` filter is appended + where the `docs-staleness` job slots in) in `specs/089-comprehensive-documentation-site/contracts/ci-integration.md` (NEW file).
- [ ] T003 [P] [W14.0] Verify the translation-vendor relationship per plan.md cross-feature coordination: confirm the same vendor used by features 083 (UI strings) and 088 (READMEs) is reusable for the docs site's User Guide / Admin Guide / Getting Started sections; the 7-day SLA from FR-602 applies. Document the vendor contact + scope (50+ pages × 5 locales = ~250 files) in `specs/089-comprehensive-documentation-site/contracts/translation-vendor-engagement.md` (NEW file).
- [ ] T004 [P] [W14.0] Cross-feature coordination check per plan.md cross-feature matrix: confirm with feature 086 (Admin Workbench) and feature 087 (Public Signup Flow) owners that their UPDs land BEFORE UPD-039's Track B authoring (User Guide + Admin Guide pages mirror those features' routes). If 086 / 087 have not landed, T046-T060 ship placeholder pages with TODO markers; the placeholders are filled in once the dependencies land. Document the coordination decisions in `specs/089-comprehensive-documentation-site/contracts/cross-feature-deps.md` (NEW file).

---

## Phase 2: Foundational Track A — Site Infrastructure (Blocks Every Page Build)

**Story goal**: Extend the existing `mkdocs.yml` with 5 plugins (i18n, mike, redirects, gen-files, mkdocstrings); add `helm-docs` Go binary install in CI; add `docs:` paths filter; add new `.github/workflows/docs-build.yml` workflow; reconcile the navigation drift (v3/v4 → v5/v6). Without these, the docs site cannot build.

### `mkdocs.yml` extensions

- [ ] T005 [W14A] Modify `requirements-docs.txt` per plan.md correction §7: add 5 new pip dependencies — `mkdocs-static-i18n>=1.2`, `mike>=2.0`, `mkdocs-redirects>=1.2`, `mkdocs-gen-files>=0.5`, `mkdocstrings[python]>=0.24`. Pin minor versions to avoid breakage. Run `pip install -r requirements-docs.txt` locally and verify all dependencies install cleanly without conflicts.
- [ ] T006 [W14A] Modify `mkdocs.yml` per plan.md design Track A: add the 5 new plugins to the `plugins:` block in this order (matters for plugin interop per plan.md research R3): `search` (existing), `mkdocs-static-i18n` (configured for the 6 supported locales — en canonical, es, de, fr, it, zh-CN per spec correction §6 + FR-620 — with `localized_sections: [getting-started, user-guide, admin-guide]`), `mike` (versioning — `default_version: latest`, `version_selector: true`), `redirects` (configured with `redirect_maps:` for the on-disk → new-structure migrations from T038-T040), `gen-files` (configured with `scripts: [docs/gen_env_vars.py, docs/gen_helm_values.py, docs/gen_openapi.py]`), `mkdocstrings` (configured with `default_handler: python`).
- [ ] T007 [W14A] Modify `mkdocs.yml`'s `nav:` block per plan.md correction §2: REPLACE the existing nav (which references outdated v3/v4 docs paths) with the FR-605 11-section structure pointing at the new directories from T038-T040 (`getting-started/`, `user-guide/`, `admin-guide/`, `operator-guide/`, `developer-guide/`, `api-reference/`, `architecture/`, `installation/`, `configuration/`, `security/`, `release-notes/`). Each section's nav points at its `index.md` + sub-pages.
- [ ] T008 [W14A] Verify the modified `mkdocs.yml` builds cleanly: run `mkdocs build --strict` locally; assert zero errors and zero warnings. Test locale switching by serving the site (`mkdocs serve`) and clicking the language toggle on a User Guide page (the toggle should appear); verify English-only sections (Architecture, Developer Guide, API Reference) hide the language toggle per FR-620 + plan.md research R7.

### `docs:` paths filter + new workflow

- [ ] T009 [W14A] Modify `.github/workflows/ci.yml` per plan.md correction §8: append the `docs: ['docs/**', 'mkdocs.yml', 'scripts/generate-env-docs.py', 'scripts/check-doc-references.py', 'scripts/export-openapi.py']` filter to the existing `dorny/paths-filter@v3` block (after the `readme:` filter from feature 088). The filter feeds the new `docs-staleness` job from T034 + the `docs-build` workflow from T010.
- [ ] T010 [W14A] Create `.github/workflows/docs-build.yml` (NEW workflow) per plan.md design Track A: triggers on `pull_request` (when the `docs:` paths-filter from T009 is true) AND on `push: { branches: [main] }`. PR mode: build via `mkdocs build --strict`, upload the `site/` artifact. Push-to-main mode: deploy via `mike deploy --push --update-aliases v1.3.0 latest` to the `gh-pages` branch (per plan.md research R10). Permissions: `contents: write` (for the gh-pages push) + `pull-requests: write` (for PR comments on build failures). Install Python 3.12, pip-install from `requirements-docs.txt`, install `helm-docs` v1.13.1 via `curl https://github.com/norwoodj/helm-docs/releases/download/v1.13.1/helm-docs_1.13.1_Linux_x86_64.tar.gz` (with checksum verification per plan.md risk-register row 8), install `pandoc` via `apt-get install -y pandoc`.

### Initial directory scaffolding (NEW empty directories)

- [ ] T011 [W14A] Create the 11 new top-level documentation directories (empty `index.md` placeholders to satisfy mkdocs-static-i18n's section detection): `docs/getting-started/index.md`, `docs/user-guide/index.md`, `docs/admin-guide/index.md`, `docs/operator-guide/index.md`, `docs/developer-guide/index.md`, `docs/api-reference/index.md`, `docs/architecture/index.md`, `docs/installation/index.md`, `docs/configuration/index.md`, `docs/security/index.md`, `docs/release-notes/index.md`. Each `index.md` is a minimal stub with the section H1 + a 2-3-sentence description (filled in T046+ by the actual content tasks).
- [ ] T012 [W14A] Create `docs/index.md` (the docs landing page) cross-linking to the README at `../README.md` + a 2-3 paragraph "Welcome to Musematic" intro + links to each of the 11 sections. The page references the architecture diagram from `docs/assets/architecture-overview.svg` (already on disk per feature 088 / plan.md correction §10).

---

## Phase 3: Foundational Track A — Auto-Generation Scripts + Helm-Docs Annotations

**Story goal**: Author the 3 auto-generation scripts (env-vars, FR-references, OpenAPI export) + add helm-docs annotations across all 16 Helm chart `values.yaml` files. This phase blocks US3 (env-var reference) + US2 (API Reference) + the FR-616 staleness CI gate.

### `scripts/generate-env-docs.py` (FR-610)

- [ ] T013 [W14A] [US3] Create `scripts/generate-env-docs.py` per plan.md research R8 + correction §13: Python stdlib + `pydantic.BaseSettings` introspection (NO new deps). Walks (a) `apps/control-plane/src/platform/common/config.py`'s 41 Pydantic Settings classes via `cls.__fields__` introspection; (b) Python `os.getenv()` calls via `ast.parse()` + visitor pattern across `apps/control-plane/src/platform/`; (c) Go `os.Getenv()` calls via regex across `services/`; (d) Helm `valueFrom: env:` references via YAML parsing across `deploy/helm/`. Outputs a deduplicated Markdown table at `docs/configuration/environment-variables.md` with columns: variable name, component, required/optional, default, description, security sensitivity (inferred from name heuristics: `*_PASSWORD`, `*_SECRET`, `*_TOKEN`, `*_KEY` → `sensitive`; `*_URL`, `*_HOST`, `*_PORT` → `configuration`; rest → `informational`). Group by component (Settings class name); scattered calls under "Other".
- [ ] T014 [W14A] [US3] Create `scripts/tests/test_generate_env_docs.py` (NEW pytest unit test file): ~10 test cases covering Pydantic Settings introspection, AST walk over a synthetic Python file with 5 `os.getenv()` calls, Go AST walk regex, deduplication when the same env var appears in code AND in Settings class, security-sensitivity heuristic correctness, output format stability (deterministic across runs).
- [ ] T015 [W14A] [US3] Run `python scripts/generate-env-docs.py` + commit the generated `docs/configuration/environment-variables.md` as the initial canonical baseline. Verify SC-016 — the AST walker completes in ≤ 30 seconds on the entire control-plane + Go satellite codebase.

### `scripts/check-doc-references.py` (FR-616)

- [ ] T016 [W14A] Create `scripts/check-doc-references.py` per plan.md research R8: scans `docs/` for `FR-NNN` regex patterns (`\bFR-\d{3}\b`); validates each FR exists in `docs/functional-requirements-revised-v6.md`; flags broken references; flags FRs that exist in the FR doc but have no doc coverage (informational warnings, NOT failures, per the brownfield's "New FRs without doc coverage produce warnings"). Exit codes: 0 (no broken refs), 1 (broken refs found), 2 (FR doc unparseable).
- [ ] T017 [P] [W14A] Create `scripts/tests/test_check_doc_references.py` (NEW pytest unit test file): ~6 test cases covering valid FR reference, broken FR reference (FR-999), undocumented FR (informational warning), FR doc unparseable (exit 2).

### Helm-docs annotations across 16 charts

- [ ] T018 [W14A] Annotate `deploy/helm/platform/values.yaml` with `helm-docs` `# --` comments per plan.md correction §12 + research R9: each documented value gets a `# -- description` comment ABOVE its key. Add a `# @section --` annotation for grouping. Run `helm-docs --chart-search-root=deploy/helm/platform/` locally to verify the annotations parse cleanly.
- [ ] T019 [P] [W14A] Annotate `deploy/helm/observability/values.yaml` + the 4 sizing-preset overlays (`values-{minimal,standard,enterprise,e2e}.yaml`) with helm-docs comments. The presets reuse the description from the base `values.yaml` for shared keys; preset-specific overrides get their own descriptions.
- [ ] T020 [P] [W14A] Annotate the remaining 14 Helm charts' `values.yaml` files: `runtime-controller`, `kafka`, `redis`, `postgresql`, `qdrant`, `neo4j`, `opensearch`, `clickhouse`, `minio`, `control-plane`, `reasoning-engine`, `simulation-controller`, `ui` (parallelizable across multiple devs — 14 separate files).
- [ ] T021 [W14A] Create `scripts/aggregate-helm-docs.py` per plan.md research R9 (BOTH per-chart README.md + aggregated page): runs `helm-docs` per chart, collects each chart's generated `README.md`, aggregates into a unified `docs/configuration/helm-values.md`. The aggregated page groups by chart with H2 headings + tables.

### `mkdocs-gen-files` hooks

- [ ] T022 [W14A] Create `docs/gen_env_vars.py` (mkdocs-gen-files hook): invokes `scripts/generate-env-docs.py` as a subprocess; output is captured and written to `docs/configuration/environment-variables.md`. The hook runs at MkDocs build time per plan.md design Track A; the committed file from T015 acts as the canonical baseline + drift-detection input.
- [ ] T023 [P] [W14A] Create `docs/gen_helm_values.py` (mkdocs-gen-files hook): invokes `scripts/aggregate-helm-docs.py` as a subprocess; output is `docs/configuration/helm-values.md`.
- [ ] T024 [P] [W14A] Create `docs/gen_openapi.py` (mkdocs-gen-files hook): reads the committed `docs/api-reference/openapi.json` (produced by T030) AND renders the Redoc + Swagger UI embeds.

---

## Phase 4: Foundational Track A — OpenAPI Export + Staleness CI Gate

**Story goal**: OpenAPI export pipeline + CI staleness checks (3 staleness checks per FR-616). Without these, US2 (API Reference) cannot work AND US3 (env-var drift) cannot be enforced.

- [ ] T025 [W14A] Create `scripts/export-openapi.py` per plan.md research R5: ~30-line Python script that imports the FastAPI app via `from platform.main import app`, calls `app.openapi()`, and writes the result to `docs/api-reference/openapi.json` using `json.dumps(spec, sort_keys=True, indent=2)` for deterministic output (per plan.md risk-register row 10). The script depends on the platform's Python environment being set up (it imports the platform module).
- [ ] T026 [P] [W14A] Run `python scripts/export-openapi.py` locally + commit the generated `docs/api-reference/openapi.json` as the initial canonical baseline. Verify the file size is reasonable (typically < 5 MB) AND that `cat docs/api-reference/openapi.json | jq '.openapi'` returns `"3.1.0"`.
- [ ] T027 [W14A] Add a CI step in `.github/workflows/docs-build.yml` (T010) that re-runs `scripts/export-openapi.py` on every PR touching `apps/control-plane/`; if the regenerated output differs from the committed snapshot, fail the build with a clear "OpenAPI spec drift — re-run scripts/export-openapi.py and commit" message. This is the FR-619 + FR-616 contract.
- [ ] T028 [W14A] Create the **`docs-staleness` CI job** in `.github/workflows/ci.yml` per plan.md research R8: conditional on `if: needs.changes.outputs.docs == 'true'`; permissions `contents: read, pull-requests: write`; runs three staleness checks as separate steps: (1) `python scripts/generate-env-docs.py > /tmp/env-vars.md && diff /tmp/env-vars.md docs/configuration/environment-variables.md` (FR-610 drift); (2) `helm-docs --check` AND `python scripts/aggregate-helm-docs.py > /tmp/helm-values.md && diff /tmp/helm-values.md docs/configuration/helm-values.md` (FR-611 drift); (3) `python scripts/check-doc-references.py docs/` (FR-616 FR-reference drift). Job fails on any non-zero exit. On failure, posts a PR comment with the diff + remediation instructions.

---

## Phase 5: Foundational Track B/C — `git mv` Migrations

**Story goal**: Migrate the 13 existing on-disk `docs/` files into the new FR-605 11-section structure via `git mv` (preserves history). This phase blocks Tracks B (User Guide / Admin Guide) and C (Architecture / Developer Guide).

- [ ] T029 [W14A] Migrate the 3 architecture-related top-level files via `git mv` (preserves history): `git mv docs/system-architecture-v5.md docs/architecture/system-architecture.md` AND `git mv docs/software-architecture-v5.md docs/architecture/software-architecture.md`. The `functional-requirements-revised-v6.md` STAYS at `docs/functional-requirements-revised-v6.md` (canonical FR document referenced by `scripts/check-doc-references.py`).
- [ ] T030 [W14A] Migrate the small `docs/agents.md` (24 lines per inventory) via `git mv docs/agents.md docs/developer-guide/building-agents.md`. The migrated file's content is preserved AS-IS; T076 extends it with feature 075 (model catalog) + feature 086 (admin workbench) cross-references.
- [ ] T031 [P] [W14A] Migrate `docs/development/structured-logging.md` via `git mv` to `docs/developer-guide/structured-logging.md`.
- [ ] T032 [P] [W14A] Migrate `docs/operations/grafana-metrics-logs-traces.md` via `git mv` to `docs/operator-guide/observability.md`.
- [ ] T033 [P] [W14A] Migrate the remaining `docs/` content: `docs/integrations/webhook-verification.md` → folded into `docs/developer-guide/mcp-integration.md` (T077); `docs/administration/audit-and-compliance.md` → folded into `docs/admin-guide/security-compliance.md` (T067); `docs/administration/integrations-and-credentials.md` → folded into `docs/admin-guide/system-config.md` (T065); `docs/features/{074,075,076}.md` → folded into `docs/release-notes/v1.3.0.md` (T084).
- [ ] T034 [W14A] Configure the `mkdocs-redirects` plugin (T006) with the explicit redirect map per plan.md design: every old path (e.g., `/system-architecture-v3.md`) redirects to its new path (e.g., `/architecture/system-architecture/`). The redirect map is a YAML block in `mkdocs.yml`'s `plugins.redirects.redirect_maps:` section. Verify by running `mkdocs build && cd site && python -m http.server 8000` then visiting `http://localhost:8000/system-architecture-v3.md` in a browser; the redirect should fire.

---

## Phase 6: User Story 3 — Environment Variables Reference (P1) 🎯 MVP VERIFICATION FOR US3

**Story goal**: The auto-generated env-var reference at `docs/configuration/environment-variables.md` is the canonical surface for super admins per FR-610; CI fails on drift.

- [ ] T035 [P] [US3] [W14C] Verify the env-var reference covers the 41 Pydantic Settings classes + scattered `os.getenv()` calls per plan.md correction §13: open `docs/configuration/environment-variables.md`; verify ≥ 100 entries (rough count: 41 Settings × ~5 fields each + 11 raw Python calls + 38 Go calls = ~250 entries deduplicated to ~150-200). Search for `PLATFORM_SUPERADMIN_PASSWORD_FILE`; verify it appears with security-sensitivity `sensitive`.
- [ ] T036 [P] [US3] [W14F] Submit a synthetic test PR adding `os.getenv("PLATFORM_NEW_VAR_FOR_TEST")` to a Python file in `apps/control-plane/src/platform/`; verify the `docs-staleness` CI job (T028) fails with a clear "env-var-doc drift" message; verify the failure message includes remediation instructions ("re-run scripts/generate-env-docs.py and commit"). Close the test PR without merging.

---

## Phase 7: User Story 2 — API Reference (P1) 🎯 MVP VERIFICATION FOR US2

**Story goal**: The API Reference embeds the OpenAPI 3.1 spec as Redoc + Swagger UI per FR-619; code samples in 4 languages.

- [ ] T037 [US2] [W14C] Author `docs/api-reference/rest-api.md` per FR-619: embeds the Redoc + Swagger UI components via the `gen_openapi.py` hook (T024). Includes (a) authentication guide referencing the existing OAuth backend at `apps/control-plane/src/platform/auth/router_oauth.py`; (b) rate-limit table per endpoint (cross-references the FR-588 signup limits + the standard limits); (c) error code catalog at `docs/api-reference/error-codes.md` (T038) with remediation suggestions per FR-583's structured-error shape; (d) API changelog with per-version backward-compatibility annotations.
- [ ] T038 [P] [US2] [W14C] Author `docs/api-reference/error-codes.md` per FR-619: ≥ 50 documented error codes with remediation suggestions. The codes mirror feature 086's error responses (`admin_role_required`, `admin_read_only_mode`, `superadmin_role_required`, etc.) + feature 087's signup error codes (`account_pending_approval`, `domain_not_permitted`, `org_not_permitted`, etc.) + the standard auth + rate-limit + validation errors.
- [ ] T039 [P] [US2] [W14C] Author `docs/api-reference/websocket-api.md`: documents the WebSocket channel types from feature 019's `ws_hub/subscription.py` ChannelType enum (extended in features 086 with admin channels) + the WebSocket auth pattern from `apps/control-plane/src/platform/auth/`.
- [ ] T040 [P] [US2] [W14C] Author `docs/api-reference/a2a-api.md` and `docs/api-reference/mcp-api.md` placeholder pages with FR-references to the relevant FR doc sections. Since A2A and MCP integrations are partial in the codebase (per inventory), these pages note "subject to change as integrations land".
- [ ] T041 [P] [US2] [W14F] Code samples in 4 languages per FR-619: for each major endpoint (≥ 20 endpoints), provide Python (`requests`), Go (`net/http`), TypeScript (`fetch`), and curl examples. Use a shared template per language; samples are inline in the Redoc embed via the `x-codeSamples` OpenAPI extension (added by T025's `export-openapi.py` script — extends T025 to inject the samples).

---

## Phase 8: Track B — Getting Started (English)

**Story goal**: Author the Getting Started section per FR-605 §1 — what-is-musematic, quick-start (5-min kind path per FR-606), glossary, first-tutorial.

- [ ] T042 [W14B] Author `docs/getting-started/what-is-musematic.md` per spec User Story 4 acceptance scenario 1 + plan.md design Track B: a clear, accessible description of Musematic's purpose, target users (consumers, creators, admins, super admins, operators, developers), and differentiators. ~ 500-700 words. Cross-links to `docs/index.md` (the docs landing page) and the README.
- [ ] T043 [P] [W14B] Author `docs/getting-started/quick-start.md` per FR-606: a 5-minute kind installation walkthrough using `make dev-up` (verified at `Makefile:38` per feature 088 inventory). Includes (a) prerequisites table (Docker, kind, Helm, kubectl versions); (b) the `git clone && cd musematic && make dev-up` flow; (c) post-install verification (open `http://localhost:8080`); (d) a clarifying note about first-run-cold-cache vs steady-state timing per plan.md correction §10.
- [ ] T044 [P] [W14B] Author `docs/getting-started/glossary.md`: ≥ 30 platform-specific terms with concise definitions (FQN, agent, bounded context, fleet, governance, observer, judge, enforcer, certification, workspace, goal, GID, etc.).
- [ ] T045 [P] [W14B] Author `docs/getting-started/first-tutorial.md`: a 30-minute tutorial walking through building, running, and observing a simple agent end-to-end. References the Developer Guide pages for deeper coverage.

---

## Phase 9: Track B — User Guide (English) — US4 Source

**Story goal**: Author the User Guide per FR-605 §2 — Consumer + Creator + Workspace Collaboration + Workbenches Overview workflows. This is the canonical English content the translation vendor (T098-T104) ships into 5 locales.

- [ ] T046 [W14B] Author `docs/user-guide/index.md` (section landing page) cross-linking to the 4 sub-sections (consumer/, creator/, workspace-collaboration/, workbenches-overview).
- [ ] T047 [P] [W14B] Author the **5 Consumer workflow pages** in parallel: `docs/user-guide/consumer/discovering-agents.md`, `starting-conversation.md`, `observing-execution.md`, `reasoning-traces.md`, `alerts.md`. Each ~ 300-500 words; cross-references to the Workbench from feature 086 + the conversation flow from feature 016.
- [ ] T048 [P] [W14B] Author the **7 Creator workflow pages** in parallel: `docs/user-guide/creator/{registering-agent, fqn, purpose-approach, visibility-tools, packaging, certification, publishing}.md`. Cross-references to feature 015's FQN convention + feature 086's admin workbench's certification queue.
- [ ] T049 [P] [W14B] Author the **4 Workspace Collaboration pages** in parallel: `docs/user-guide/workspace-collaboration/{goals, multi-agent, attention, gid-correlation}.md`. Cross-references to feature 014's GID semantics.
- [ ] T050 [W14B] Author `docs/user-guide/workbenches-overview.md`: the overview of all 4 workbenches (Operator, Trust, Admin, Super Admin) with cross-references to the dedicated guides for each.

---

## Phase 10: Track B — Admin Guide (English) — Mirrors Feature 086

**Story goal**: Author 10 Admin Guide pages mirroring FR-548 through FR-557 (Admin Workbench sections from feature 086). Per plan.md cross-feature coordination, feature 086 must land before this phase.

- [ ] T051 [W14B] Author `docs/admin-guide/index.md` + the 10 sub-pages (one per FR-548-557 section per plan.md design Track B): `identity-access.md`, `tenancy-workspaces.md`, `system-config.md`, `security-compliance.md`, `operations-health.md`, `cost-billing.md`, `observability.md`, `integrations.md`, `lifecycle.md`, `audit-logs.md`. Each page documents the corresponding admin workbench page from feature 086 with screenshots (English first; localized versions follow in T100).
- [ ] T052 [P] [W14B] Per page in T051, include a "Common admin workflows" subsection with 3-5 walkthroughs (e.g., on `identity-access.md`: bulk-suspend users + force MFA enrollment + revoke all sessions). The walkthroughs cross-reference feature 086's bulk-action + impersonation + 2PA flows.

---

## Phase 11: User Story 5 — Operator Guide + Runbook Library (P1)

**Story goal**: Author the FR-617 runbook library with 10 runbooks + the Operator Guide section per FR-605 §4. Each runbook has Symptom / Diagnosis / Remediation / Verification sections.

### Operator Guide supporting pages

- [ ] T053 [W14D] Author `docs/operator-guide/index.md` + cross-links to 6 supporting pages: `observability.md` (REUSES T032's migrated content), `dashboards-reference.md` (the 22 Grafana dashboards from feature 084 / UPD-034 + the 1 trust-content-moderation per feature 088 / plan.md correction §1), `incident-response.md`, `capacity-planning.md`, `backup-restore.md`, `multi-region-failover.md`, `logql-cookbook.md`.
- [ ] T054 [P] [W14D] Author `docs/operator-guide/dashboards-reference.md`: enumerate the 22 dashboards from feature 084 + 1 from feature 078 with each dashboard's purpose + key panels + on-call relevance. Cross-references the Grafana embed from `docs.musematic.ai/api-reference/` (T037).

### 10 Runbooks per FR-617

- [ ] T055 [P] [US5] [W14D] Author `docs/operator-guide/runbooks/platform-upgrade.md`: Symptom (operators want to deploy a new platform version) / Diagnosis (review release notes + breaking-change inventory) / Remediation (rolling Helm upgrade with `--wait`) / Verification (`platform-cli observability status` + smoke tests).
- [ ] T056 [P] [US5] [W14D] Author `docs/operator-guide/runbooks/database-migration-rollback.md`: covers Alembic `migrate-rollback` flow per the existing `Makefile` target.
- [ ] T057 [P] [US5] [W14D] Author `docs/operator-guide/runbooks/disaster-recovery-restore.md`: restore from S3 backup per feature 048's contract.
- [ ] T058 [P] [US5] [W14D] Author `docs/operator-guide/runbooks/multi-region-failover-failback.md`: covers feature 081's failover orchestrator + the 2PA-required execution per FR-561 + UPD-036's admin workbench.
- [ ] T059 [P] [US5] [W14D] Author `docs/operator-guide/runbooks/secret-rotation.md`: covers feature 074 / UPD-024's secret rotation workflow.
- [ ] T060 [P] [US5] [W14D] Author `docs/operator-guide/runbooks/capacity-expansion.md`: adding worker nodes via Terraform (cross-references T091).
- [ ] T061 [P] [US5] [W14D] Author `docs/operator-guide/runbooks/super-admin-break-glass.md`: covers FR-579's `platform-cli superadmin recover` + the emergency-key file path per feature 086 / UPD-036.
- [ ] T062 [P] [US5] [W14D] Author `docs/operator-guide/runbooks/incident-response-procedures.md`: covers feature 080 / UPD-031's incident-response BC + the dashboard's "View runbook" deep-link integration per plan.md cross-feature coordination row 6.
- [ ] T063 [P] [US5] [W14D] Author `docs/operator-guide/runbooks/log-query-cookbook.md` (LogQL cookbook per FR-617): ≥ 20 common LogQL queries for the 22 Grafana dashboards from feature 084.
- [ ] T064 [P] [US5] [W14D] Author `docs/operator-guide/runbooks/tls-emergency-renewal.md`: covers FR-614's emergency manual TLS renewal procedure (when cert-manager auto-renewal fails).
- [ ] T065 [W14D] Author `docs/operator-guide/runbooks/index.md` listing all 10 runbooks with one-line summaries + symptom keywords for searchability per spec User Story 5 acceptance scenario 1.

---

## Phase 12: Track C — Architecture + Developer Guide (English)

**Story goal**: Author the Architecture section per FR-605 §7 and the Developer Guide per FR-605 §5. Both English-only per FR-620.

- [ ] T066 [W14C] Modify the migrated `docs/architecture/system-architecture.md` (from T029): add a navigation header at the top + cross-links to the bounded-contexts catalog from T067 + the architecture diagram from `docs/assets/architecture-overview.svg`.
- [ ] T067 [P] [W14C] Author `docs/architecture/bounded-contexts/` directory (one page per BC): ~ 30 BC pages (auth, accounts, workspaces, registry, governance, audit, notifications, …, incident_response, multi_region_ops, security_compliance, privacy_compliance, cost_governance, model_catalog, etc.). Each page is ~ 200-300 words covering the BC's responsibility, primary entities, REST surface, Kafka topics, FR references.
- [ ] T068 [P] [W14C] Author `docs/architecture/data-stores.md`, `event-topology.md`, `security-trust-privacy.md`, `observability-architecture.md`, `architecture-decisions.md`. The architecture-decisions page enumerates AD-1 through AD-23 + audit-pass ADs (the constitutional AD inventory).
- [ ] T069 [W14C] Author `docs/developer-guide/index.md` + 8 sub-pages: `agent-card-spec.md`, `contract-authoring.md`, `tool-gateway.md`, `mcp-integration.md` (folds in the migrated `webhook-verification.md` content from T033), `a2a-integration.md`, `sdk-usage.md`, `reasoning-primitives.md`, `evaluation-authoring.md`, `self-correction-tuning.md`. The migrated `building-agents.md` (T030) and `structured-logging.md` (T031) stay at their post-migration paths.
- [ ] T070 [W14C] Extend the migrated `docs/developer-guide/building-agents.md` per plan.md correction §11: add cross-references to feature 075 (model catalog) + feature 086 (admin workbench's model-catalog page).

---

## Phase 13: Track C — Configuration Reference + Security Guide

**Story goal**: Author the Configuration Reference section (env vars + Helm values + feature flags + URL scheme + TLS strategy + networking) and the Security Guide section per FR-605 §10 + FR-618.

### Configuration Reference

- [ ] T071 [W14C] Author `docs/configuration/index.md` cross-linking to the 6 sub-pages.
- [ ] T072 [P] [W14C] Author `docs/configuration/feature-flags.md` per FR-612: enumerate every feature flag from the FR-584 inventory (UPD-036) + every additional flag added by UPD-036 / 037 / 038 / 039. Each flag has columns: name, default, scope (platform / tenant / workspace / user), controlled-by-role, description, related FRs, rollout history.
- [ ] T073 [P] [W14C] Author `docs/configuration/url-scheme.md` per FR-613: documents the canonical production URLs (`app.musematic.ai`, `api.musematic.ai`, `grafana.musematic.ai`) + dev URLs (`dev.*.musematic.ai`) + per-environment pattern + CORS policy + cookie-domain separation.
- [ ] T074 [P] [W14C] Author `docs/configuration/tls-strategy.md` per FR-614: Let's Encrypt DNS-01 wildcard + cert-manager + renewal alerting + emergency manual renewal cross-link to T064.
- [ ] T075 [P] [W14C] Author `docs/configuration/networking.md`: firewall rules + CORS policy details + NetworkPolicy defaults from feature 086.

### Security Guide + `SECURITY.md`

- [ ] T076 [W14C] Author `SECURITY.md` at the repo root per FR-618 + plan.md correction §5: includes (a) responsible-disclosure policy; (b) the email alias `security@musematic.ai`; (c) PGP key reference (operator-driven task to generate the key + publish at `https://musematic.ai/.well-known/security.txt` per the brownfield's security note); (d) response SLA (initial ack ≤ 24 business hours, remediation plan ≤ 5 business days). The file links to the docs site's full Security Guide section.
- [ ] T077 [P] [W14C] Author `docs/security/index.md` + 4 sub-pages per FR-618: `threat-model.md` (with trust boundaries across planes), `compliance-mapping.md` (SOC2 / ISO27001 / GDPR / HIPAA / PCI mapping with links to feature 074 / UPD-024's audit chain evidence substrate), `best-practices.md`, `responsible-disclosure.md` (mirrors the repo-root `SECURITY.md` content).

---

## Phase 14: Track D — Hetzner Installation Guide (US1) + Terraform Modules

**Story goal**: Author the FR-608 Hetzner installation guide end-to-end + commit the Terraform modules per plan.md correction §4 + research R6.

### Terraform modules (NEW per plan correction §4)

- [ ] T078 [W14D] Create `terraform/modules/hetzner-cluster/` per plan.md design Track D: `main.tf` (Hetzner Cloud resources: 1 control plane + 3 workers + private network + firewall + Hetzner Cloud LB), `variables.tf` (per the brownfield example tfvars: `cluster_name`, `control_plane_count`, `worker_count`, `control_plane_server_type`, `worker_server_type`, `network_zone`, `firewall_allowed_cidrs`, `load_balancer_type`, `ssh_public_key_file`), `outputs.tf` (LB IPv4/IPv6, control-plane IPs, kubeconfig path).
- [ ] T079 [P] [W14D] Create `terraform/environments/production/{main.tf, variables.tf, terraform.tfvars.example}` referencing the module from T078 with production-tier defaults (`dedicated-ccx33` control plane, `dedicated-ccx53` workers, EU central region).
- [ ] T080 [P] [W14D] Create `terraform/environments/dev/{main.tf, variables.tf, terraform.tfvars.example}` with dev-tier defaults (`cax11` server type for cost efficiency).
- [ ] T081 [P] [W14D] Add a CI step in `.github/workflows/ci.yml` (T009) that runs `terraform fmt -check && terraform validate` per plan.md open question Q6 — NOT `terraform apply` (too expensive); the apply path is verified during the quarterly Hetzner deployment per T106.

### Hetzner installation guide

- [ ] T082 [US1] [W14D] Author `docs/installation/hetzner.md` (the flagship FR-608 guide, ~1500 lines) per plan.md design Track D — Hetzner architecture diagram. The guide follows the 10-step structure: Prerequisites → Step 1 Terraform → Step 2 kubeadm → Step 3 addons → Step 4 DNS records (canonical URL scheme per T073) → Step 5 TLS (cross-link to T074) → Step 6 observability (helm install observability per UPD-035) → Step 7 platform Helm install → Step 8 super admin bootstrap (per UPD-036) → Step 9 verification → Step 10 production hardening + Troubleshooting section.
- [ ] T083 [P] [US1] [W14D] Author the troubleshooting section of `docs/installation/hetzner.md` per spec User Story 1 acceptance scenario 3 + the brownfield's "Troubleshooting" enumeration: DNS propagation delays, Let's Encrypt rate limits, MetalLB / Hetzner LB IP conflicts, Longhorn PV scheduling issues, kubeadm certificate expiry, time drift on worker nodes — each with diagnostic steps + remediation.
- [ ] T084 [P] [US1] [W14D] Author the production-hardening section: NetworkPolicy defaults, backup to Hetzner Storage Box, log retention 14d hot / 90d cold, alerting routing, node auto-recovery, periodic failover test cadence (cross-link to T058 multi-region runbook).

---

## Phase 15: Track D — Other Installation Guides (kind / k3s / Managed K8s)

**Story goal**: Author the remaining 3 installation guides per FR-606 / FR-607 / FR-609 + air-gapped guide.

- [ ] T085 [W14D] Author `docs/installation/index.md` (overview of 4 deployment paths) + a comparison table.
- [ ] T086 [P] [W14D] Author `docs/installation/kind.md` per FR-606: 15-minute target. The guide REUSES the canonical `make dev-up` flow from T043's quick-start; extends with kind-config.yaml details + observability install + seed data.
- [ ] T087 [P] [W14D] Author `docs/installation/k3s.md` per FR-607: single-node k3s on Ubuntu 22.04+ with Traefik (bundled) + cert-manager.
- [ ] T088 [P] [W14D] Author `docs/installation/managed-k8s.md` per FR-609: GKE / EKS / AKS unified guide with per-cloud sections covering IAM, VPC, node pools, storage classes, cloud-native LB.
- [ ] T089 [P] [W14D] Author `docs/installation/air-gapped.md` per the brownfield's "Air-gapped installations" enumeration: image mirror setup + offline Helm install + offline secret seeding.

---

## Phase 16: Release Notes + Cross-Cutting Pages

- [ ] T090 [W14C] Author `docs/release-notes/v1.3.0.md` per plan.md correction §16: summarizes the v1.3.0 cohort (UPD-036 / UPD-037 / UPD-038 / UPD-039) + folds in the migrated content from `docs/features/{074,075,076}.md` (T033). The root `CHANGELOG.md` is preserved unchanged + symlinked / mirrored as `docs/release-notes/changelog.md` per FR-605 §11.

---

## Phase 17: User Story 4 — Translation + Native-Speaker Review (P2)

**Story goal**: User-facing sections (Getting Started + User Guide + Admin Guide) translated into 5 locales per FR-620 + native-speaker review per locale ≥ 4/5 quality rating.

### Vendor commission + delivery

- [ ] T091 [W14E] Submit the canonical English User-facing content (T042-T052 outputs) to the translation vendor per plan.md research R11 + cross-feature coordination. Scope: ~ 50 pages covering Getting Started + User Guide + Admin Guide. Locales: Spanish (neutral Latin American), German, French (France), Italian, Simplified Chinese — NOT Japanese per spec correction §6 + FR-620. The vendor's 7-day SLA per locale applies. Track the engagement in `specs/089-comprehensive-documentation-site/contracts/translation-vendor-engagement.md` (T003) with the submission timestamp + per-locale expected delivery dates.
- [ ] T092 [W14E] Receive translated MDX/Markdown files from the vendor; place them under `docs/{getting-started,user-guide,admin-guide}/` with the locale-suffix convention from `mkdocs-static-i18n` (e.g., `docs/getting-started/index.es.md`, `docs/getting-started/index.de.md`, etc. per plan.md open question Q4).

### Per-locale verification

- [ ] T093 [P] [US4] [W14E] Run `mkdocs build --strict` after each locale's files land; verify the build succeeds + the language toggle renders correctly per FR-615 + spec User Story 4 acceptance scenario 1.
- [ ] T094 [P] [US4] [W14E] Recruit a native-speaker reviewer per locale per plan.md research R10 (matches feature 088's pattern); send each reviewer the corresponding `docs/{getting-started,user-guide,admin-guide}/*.{lang}.md` files; ask each to (a) read top-to-bottom; (b) rate translation quality on 1-5 scale; (c) flag awkward phrasings + technical inaccuracies; (d) verify all sections are present + the language-switcher works. Record the reviews in `specs/089-comprehensive-documentation-site/contracts/translation-quality-reviews.md` (NEW file) per spec SC-003 pattern.
- [ ] T095 [P] [US4] [W14E] Iterate with the vendor on any locale rated < 4/5: send back the reviewer's feedback; receive the revised files; re-run `mkdocs build --strict`; re-submit to the reviewer. Repeat until each locale rates ≥ 4/5.
- [ ] T096 [US4] [W14E] Configure the docs-translation parity check per plan.md research R8 + Constitution Rule 38: extend feature 088's `scripts/check-readme-parity.py` pattern to scan `docs/{getting-started,user-guide,admin-guide}/` for drift between the canonical English and the 5 localized variants. The check is a NEW step in the `docs-staleness` CI job (T028) — extends the existing 3 staleness checks to 4. The 7-day grace window per FR-602 applies.

---

## Phase 18: Verification + Deploy

**Story goal**: End-to-end verification of each installation guide + GitHub Pages deploy + final cross-review.

- [ ] T097 [P] [US1] [W14F] Verify the Hetzner installation guide end-to-end per spec User Story 1 + SC-004: on a fresh Hetzner Cloud account, follow `docs/installation/hetzner.md` step-by-step from T082; verify (a) Terraform provisioning completes within 30 minutes; (b) kubeadm bootstrap completes within 20 minutes; (c) addons install within 15 minutes; (d) observability + platform Helm installs complete within 30 minutes; (e) DNS + TLS within 30 minutes; (f) `https://app.musematic.ai` loads (or the dev domain pattern) within 3 hours total. Record the verification in `specs/089-comprehensive-documentation-site/contracts/hetzner-install-verification.md` per SC-004.
- [ ] T098 [P] [W14F] Verify the kind installation guide end-to-end per FR-606 + SC-002: on a fresh laptop with Docker + kind installed, follow `docs/installation/kind.md`; verify the platform reaches a working state in ≤ 15 minutes per the FR-606 target.
- [ ] T099 [P] [W14F] Verify the k3s installation guide end-to-end per FR-607 + SC-003: on a fresh Ubuntu 22.04+ VM, follow `docs/installation/k3s.md`; verify the platform reaches a working state in ≤ 30 minutes.
- [ ] T100 [P] [W14F] Verify the managed K8s installation guide on at least one of GKE / EKS / AKS per FR-609 + SC-005: choose one cloud (e.g., GKE Autopilot for ease); follow the cloud-specific section of `docs/installation/managed-k8s.md`; verify the platform reaches a working state. Document the chosen cloud + steps in `specs/089-comprehensive-documentation-site/contracts/managed-k8s-verification.md`.
- [ ] T101 [W14F] Run the full docs-build CI job locally: `mkdocs build --strict`; verify zero errors and warnings; the `site/` directory is populated; all 11 sections + their 50+ pages + 5 locales render correctly.
- [ ] T102 [W14F] Deploy to GitHub Pages via `mike deploy --push --update-aliases v1.3.0 latest` per plan.md research R10 + T010's workflow. Verify `https://gntik-ai.github.io/musematic/v1.3.0/` and `https://gntik-ai.github.io/musematic/latest/` both load correctly.

---

## Phase 19: Polish + CI Gates + Cross-Feature Coordination

- [ ] T103 [P] [W14G] Run the docs-staleness CI gate (T028) on the post-merge state: assert all three checks pass (env-var no drift, Helm-values no drift, FR-references no drift). If any fail, regenerate the affected file + commit.
- [ ] T104 [P] [W14G] Run axe-core scan on the deployed docs site per FR-488 + SC-015: visit each of the 11 top-level sections + a sampling of sub-pages; assert zero AA violations. The axe-core scan reuses feature 085's `axe-playwright-python` pattern. Record results in `specs/089-comprehensive-documentation-site/contracts/accessibility-scan.md`.
- [ ] T105 [P] [W14G] Run the weekly external-link validation (extending feature 088's `docs-external-links.yml` per plan.md correction §5): extend the workflow's path glob to include `docs/**/*.md`. The first run after T102's deploy should report zero broken external links; if any report, file follow-up issues.
- [ ] T106 [W14G] Schedule the quarterly Hetzner deployment validation per plan.md research R6 + risk-register row 11: a recurring task runs the full Hetzner installation guide end-to-end against a fresh Hetzner test account. Document the schedule + escalation path in `specs/089-comprehensive-documentation-site/contracts/quarterly-validation-schedule.md`.
- [ ] T107 [P] [W14G] Update `CLAUDE.md` per the speckit convention: append "Recent Changes" with a 1-2 line summary of UPD-039's contributions; record the 16 brownfield-input corrections from plan.md correction list as future-planner reference.
- [ ] T108 [W14G] Final cross-review per the brownfield's "Final cross-review: product, engineering, compliance lead": (a) product reviews user-facing pages for tone + accuracy; (b) engineering reviews technical pages for correctness; (c) compliance reviews the Security Guide + SECURITY.md per FR-618. Record sign-offs in this task's commit message.
- [ ] T109 [W14G] Operator README addendum at `specs/089-comprehensive-documentation-site/quickstart.md` (NEW): a small operator-focused walkthrough explaining how to (a) author a new doc page; (b) handle the 7-day translation grace window + drift-tracking issue lifecycle; (c) regenerate auto-generated reference content; (d) trigger a docs site re-deploy.
- [ ] T110 [W14G] Cross-feature coordination final sign-off: confirm with feature 086 / 087 / 088 owners that the Track B Admin Guide + User Guide + README cross-links are correct + complete; confirm with feature 080 owner that the runbook deep-link pattern (`docs.musematic.ai/operator-guide/runbooks/{slug}`) works from the incident dashboard. Record sign-offs in this task's commit message.

---

## Task Count Summary

| Phase | Range | Count | Wave | Parallelizable |
|---|---|---|---|---|
| Phase 1 — Setup | T001-T004 | 4 | W14.0 | yes |
| Phase 2 — Track A Site infrastructure | T005-T012 | 8 | W14A.1 | mostly sequential |
| Phase 3 — Track A Auto-gen scripts + helm-docs annotations | T013-T024 | 12 | W14A.2 | mostly parallel |
| Phase 4 — Track A OpenAPI + staleness CI | T025-T028 | 4 | W14A.3 | sequential |
| Phase 5 — `git mv` migrations | T029-T034 | 6 | W14A.4 | mostly parallel |
| Phase 6 — US3 P1 Env-var reference verification | T035-T036 | 2 | W14F | yes |
| Phase 7 — US2 P1 API Reference | T037-T041 | 5 | W14C | mostly parallel |
| Phase 8 — Getting Started (English) | T042-T045 | 4 | W14B | mostly parallel |
| Phase 9 — User Guide (English) | T046-T050 | 5 | W14B | mostly parallel |
| Phase 10 — Admin Guide (English) | T051-T052 | 2 | W14B | parallel |
| Phase 11 — US5 P1 Operator Guide + Runbook Library | T053-T065 | 13 | W14D | mostly parallel (10 runbooks) |
| Phase 12 — Track C Architecture + Developer Guide | T066-T070 | 5 | W14C | mostly parallel |
| Phase 13 — Configuration Reference + Security Guide | T071-T077 | 7 | W14C | mostly parallel |
| Phase 14 — US1 P1 Hetzner installation + Terraform | T078-T084 | 7 | W14D | mostly parallel |
| Phase 15 — Other installation guides | T085-T089 | 5 | W14D | parallel |
| Phase 16 — Release notes | T090 | 1 | W14C | n/a |
| Phase 17 — US4 P2 Translation + native review | T091-T096 | 6 | W14E | parallel (5 locales) |
| Phase 18 — Verification + deploy | T097-T102 | 6 | W14F | mostly parallel |
| Phase 19 — Polish + CI gates | T103-T110 | 8 | W14G | mostly parallel |
| **Total** | | **110** | | |

## MVP Definition

**The MVP is US1 (Phase 14 — Hetzner installation guide end-to-end verified) + US3 (Phase 6 — env-var reference auto-gen with CI staleness gate) + US5 (Phase 11 — runbook library).** Without US1 + US3 + US5, the docs site is not a viable production-deployment surface. After the MVP lands, US2 (API Reference) + US4 (5-locale localization) layer on as quality enhancements.

## Dependency Notes

- **T001-T004 (Setup) → all phases**: inventory + CI plan + vendor engagement + cross-feature coordination must be confirmed before any track starts.
- **T005-T012 (Track A site infrastructure) → all content tasks**: the MkDocs config + plugins + nav + new directories must exist before any page authoring.
- **T013-T028 (Track A auto-gen scripts + CI gate) → US3 verification + every PR after this lands**: the staleness CI gate must exist before subsequent PRs can be safely merged.
- **T029-T034 (`git mv` migrations) → Track B + Track C content**: the existing files must be in their new homes before T046+ extend them.
- **T078-T081 (Terraform modules) → T082 (Hetzner installation guide)**: the modules must exist before the guide references them.
- **T046-T052 (canonical English User-facing content) → T091-T095 (translation)**: the canonical English content is the input the vendor consumes.
- **Feature 086 (Admin Workbench) → T051 (Admin Guide)**: the admin workbench's pages must land before the guide can document them; if 086 is incomplete, T051 ships placeholders with TODO markers per T004's coordination notes.
- **Feature 087 (Public Signup Flow) → T046-T050 (User Guide)**: the signup + OAuth flows must land before the User Guide can document them.
- **Feature 088 (Multilingual README) → T012 (docs landing page)**: the README + the architecture diagram from feature 088 are reused.

## Constitutional Audit Matrix

| Constitution rule / FR | Verified by | Phase |
|---|---|---|
| Rule 36 — Every new FR with UX impact must be documented | T016 + T028 (FR-reference drift CI gate) | Phase 4 |
| Rule 37 — Env vars / Helm values / feature flags auto-documented | T013-T015 (env-vars), T018-T024 (helm-docs), T072 (feature flags), T028 (CI gate) | Phase 3 + 4 + 13 |
| Rule 38 — Multi-language parity enforced | T096 (docs-translation parity check extending feature 088's pattern) | Phase 17 |
| Rule 29 — Admin endpoints segregated | T051 Admin Guide documents the segregated endpoints from feature 086 | Phase 10 |
| FR-605 — 11 top-level sections | T011 + T012 + Phases 8-13 cover all 11 | All content phases |
| FR-606 — kind installation guide ≤ 15 min | T086 + T098 verification | Phase 15 + 18 |
| FR-607 — k3s installation guide | T087 + T099 verification | Phase 15 + 18 |
| FR-608 — Hetzner installation guide ≤ 3 hours | T078-T084 + T097 verification | Phase 14 + 18 |
| FR-609 — Managed K8s installation guide | T088 + T100 verification | Phase 15 + 18 |
| FR-610 — Env vars reference auto-generated | T013-T015 + T028 CI gate | Phase 3 + 4 |
| FR-611 — Helm values reference auto-generated | T018-T024 + T028 CI gate | Phase 3 + 4 |
| FR-612 — Feature flag reference | T072 | Phase 13 |
| FR-613 — URL scheme documentation | T073 | Phase 13 |
| FR-614 — TLS strategy documentation | T074 + T064 emergency renewal runbook | Phase 13 + 11 |
| FR-615 — Site technology + search + versioning + dark mode + AA | T005-T012 + T104 axe scan | Phase 2 + 19 |
| FR-616 — CI staleness detection | T028 docs-staleness job | Phase 4 |
| FR-617 — Operator runbook library ≥ 10 runbooks | T055-T064 (10 runbooks) + T065 index | Phase 11 |
| FR-618 — Security Guide + SECURITY.md | T076 + T077 | Phase 13 |
| FR-619 — API Reference quality | T037-T041 | Phase 7 |
| FR-620 — Localization policy | T091-T096 | Phase 17 |
| Wave 14 capstone | All tasks tagged W14.0 / W14A / W14B / W14C / W14D / W14E / W14F / W14G | All |
