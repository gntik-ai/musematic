# Implementation Plan: UPD-039 — Comprehensive Documentation Site and Installation Guides

**Branch**: `089-comprehensive-documentation-site` | **Date**: 2026-04-27 | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

## Summary

UPD-039 is the largest documentation feature in v1.3.0 by content volume: it converts the existing skeletal `docs/` tree (13 .md files + 1 SVG across 7 directories — verified per inventory) into the **11-section FR-605 documentation site**, ships **3 auto-generation tools** (env vars + Helm values + FR-reference drift detection), authors **4 installation guides** (kind / k3s / Hetzner / managed K8s), authors the **FR-617 runbook library of ≥ 10 runbooks**, creates **`SECURITY.md`** at the repo root + the corresponding Security Guide section per FR-618, and embeds the **OpenAPI 3.1 spec** as a browseable API Reference per FR-619 with code samples in 4 languages. It is delivered in four parallelizable tracks that converge for translation + final polish:

- **Track A — Site infrastructure** (~3.5 dev-days): extends the existing `mkdocs.yml` (verified — Material theme + 16 features + search plugin already configured) with the **i18n plugin** (`mkdocs-static-i18n`), the **versioning plugin** (`mike`), the **redirects plugin** (`mkdocs-redirects`), and the **gen-files plugin** (`mkdocs-gen-files` for OpenAPI / env-var / Helm-values auto-generation per FR-619 / FR-610 / FR-611). Adds a NEW `.github/workflows/docs-build.yml` workflow building the site on every PR touching `docs/` AND deploying to GitHub Pages on push to `main` (the existing `docs-external-links.yml` from feature 088 is preserved unchanged). Adds a `docs:` path filter to the existing `dorny/paths-filter@v3` block in `ci.yml`.
- **Track B — User-facing documentation** (~5 dev-days): authors Getting Started + User Guide + Administrator Guide + Glossary + first-tutorial + ≥ 50 pages of role-specific workflows (consumer / creator / workspace collaboration / workbenches overview); reuses the `docs/assets/architecture-overview.svg` already created by feature 088 (verified per inventory) for the Architecture overview cross-link.
- **Track C — Technical documentation** (~3.5 dev-days): migrates the on-disk `software-architecture-v5.md` (1651 lines) + `system-architecture-v5.md` (2284 lines) into the new `docs/architecture/` section via `git mv` (preserves history); authors the Developer Guide with bounded-contexts catalog + reasoning primitives + SDK usage; embeds the OpenAPI 3.1 spec via Redoc at `docs/api-reference/` per FR-619.
- **Track D — Installation guides** (~6 dev-days): authors the FR-606/607/608/609 installation guides; the flagship **Hetzner guide** (FR-608) is the largest single artefact at ~1500 lines covering Terraform infrastructure provisioning + kubeadm bootstrap + addons (MetalLB + NGINX + cert-manager + Longhorn) + DNS records (canonical `app.musematic.ai` / `api.musematic.ai` / `grafana.musematic.ai` per FR-613) + TLS (Let's Encrypt DNS-01 wildcard per FR-614) + observability install (per UPD-035) + platform install + super-admin bootstrap (per UPD-036) + verification + production hardening + troubleshooting. The Hetzner Terraform modules are NEW in this feature per plan correction §4 (no `terraform/` exists on disk).

The four tracks converge in Phase 9 for translation (User-facing sections in 6 locales per FR-620) + final polish (cross-review + GitHub Pages deploy + Hetzner verification on a live deployment).

## Constitutional Anchors

This plan is bounded by the following Constitution articles. Each implementation step below cites the article it serves.

| Anchor | Citation | Implementation tie |
|---|---|---|
| **UPD-039 declared** | Constitution lines 7-8 (audit-pass roster) | The whole feature |
| **Rule 36 — Every new FR with UX impact must be documented** | Constitution line 226 | T065's `scripts/check-doc-references.py` enforces FR-reference drift detection per FR-616 |
| **Rule 37 — Env vars, Helm values, feature flags are auto-documented** | Constitution line 228 | T060 `scripts/generate-env-docs.py` (FR-610), T070 `helm-docs` (FR-611), T078 manual feature-flags reference (FR-612) |
| **Rule 38 — Multi-language parity enforced** | Constitution line 232 | T087 docs-translation drift detection mirrors feature 088's pattern; 7-day grace window per FR-602 |
| **Rule 29 — Admin endpoints segregated** | Constitution line 193 | The Administrator Guide (T150-T160) documents the segregated admin endpoints from feature 086 |
| **FR-605 — 11 top-level sections** | FR doc lines 2241-2253 | T100-T280 phase structure mirrors the 11 sections |
| **FR-606/607/608/609 — 4 installation guides** | FR doc lines 2255-2279 | T230-T260 (Track D) |
| **FR-610/611/612 — Auto-generated config reference** | FR doc lines 2281-2289 | T060 + T070 + T078 |
| **FR-613/614 — URL scheme + TLS strategy** | FR doc lines 2290-2299 | T072 + T074 |
| **FR-615 — Site technology** | FR doc lines 2301-2302 | T010-T030 (Track A) |
| **FR-616 — CI staleness detection** | FR doc lines 2304-2305 | T060 + T065 + T070 + T085 |
| **FR-617 — Runbook library ≥ 10 runbooks** | FR doc lines 2307-2308 | T270-T280 (10 sub-tasks per runbook) |
| **FR-618 — Security Guide + `SECURITY.md`** | FR doc lines 2310-2311 | T080 + T210 |
| **FR-619 — API reference quality** | FR doc lines 2313-2314 | T076-T077 |
| **FR-620 — Localization policy** | FR doc lines 2316-2317 | Track B + T087 (Phase 10) |

## Technical Context

| Item | Value |
|---|---|
| **Languages** | Markdown (the docs content), Python 3.12 (the auto-generation scripts: stdlib + Pydantic for env-var introspection), YAML (CI workflows + Helm-docs annotations), HCL (Terraform — Hetzner modules NEW in this feature per plan correction §4). No application code. |
| **Primary Dependencies (existing — reused)** | `mkdocs==1.6.1`, `mkdocs-material==9.5.45`, `pymdown-extensions==10.12` (verified per `requirements-docs.txt` inventory); the existing `dorny/paths-filter@v3` action; the existing `gh` CLI in CI runners; `pandoc` (apt-installable, used by feature 088's parity-check); `markdown-link-check` (npm — used by feature 088's external-link workflow). |
| **Primary Dependencies (NEW in 089)** | Python: `mkdocs-static-i18n` (FR-620 i18n), `mike` (FR-615 versioning), `mkdocs-redirects` (FR-605 docs-tree reorganization preservation), `mkdocs-gen-files` (FR-610/611/619 auto-gen), `mkdocstrings[python]` (FR-619 inline Python docstring rendering for Developer Guide). External binary: `helm-docs` v1.13+ (Go binary, installed via `curl` release-binary download in CI per plan correction §7). |
| **Storage** | None at the platform layer. The docs site is statically generated; deployment artefact is the `site/` directory (per `mkdocs.yml`'s `site_dir: site` setting) pushed to the `gh-pages` branch via `mike deploy --push` per plan.md research R10. |
| **Testing** | The auto-generation scripts at `scripts/generate-env-docs.py` and `scripts/check-doc-references.py` have pytest unit tests at `scripts/tests/test_generate_env_docs.py` and `scripts/tests/test_check_doc_references.py`; the docs site itself is verified via the MkDocs build + `markdown-link-check` over internal links + axe-core scan over the deployed site per FR-488 + FR-526. |
| **Target Platform** | The docs site runs as static HTML rendered by GitHub Pages (initially per spec correction §7); migration to a Hetzner-hosted instance at `docs.musematic.ai` is a follow-up DNS task. |
| **Project Type** | Documentation feature with light tooling. No application code, no migrations. |
| **Performance Goals** | Docs site build completes in ≤ 5 minutes on `ubuntu-latest` runners; page load ≤ 800 ms p95 on a CDN-fronted site (GitHub Pages includes CDN); search response ≤ 500 ms p95 per SC-011. The `scripts/generate-env-docs.py` AST walker over the entire control-plane + Go satellite codebase completes in ≤ 30 seconds per SC-016. |
| **Constraints** | FR-616 CI staleness detection — the docs-build job MUST fail on env-var-doc drift / Helm-values-doc drift / FR-reference drift; FR-620 — User-facing sections in 6 locales (English, Spanish, German, French, Italian, Simplified Chinese — NOT Japanese per spec correction §6); FR-619 — the OpenAPI spec is auto-fetched from `apps/control-plane/src/platform/main.py`'s FastAPI `app.openapi()` (NO static export on disk per inventory; per plan research R5, UPD-039 snapshots the spec at build time via a small `scripts/export-openapi.py` script). |
| **Scale / Scope** | Track A: 1 modified `mkdocs.yml` + 1 new docs-build workflow + 5 new pip dependencies + `helm-docs` binary install. Track B: ~50 user-facing pages + 6 locales = ~150 markdown files post-translation. Track C: ~30 technical pages including the migrated v5 architecture docs (3935 lines combined) + bounded-contexts catalog + Developer Guide. Track D: 4 installation guides totalling ~3000 lines (Hetzner alone is ~1500) + Terraform modules per plan correction §4 (~600 lines HCL). FR-617 runbook library: 10 runbooks averaging ~200 lines each = ~2000 lines. **Total: ~5000-7000 lines of new English content + auto-generated reference content + 50+ user-facing pages × 5 localized variants.** |

## Constitution Check

> **GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.**

| Check | Verdict | Rationale |
|---|---|---|
| Brownfield rule — modifications respect existing repo discipline | ✅ Pass | UPD-039 EXTENDS the existing `mkdocs.yml`, REORGANIZES the existing `docs/` tree via `git mv` (preserves history), CREATES new files at well-defined paths (`docs/security/`, `docs/configuration/`, `docs/installation/`, `docs/api-reference/`, `docs/architecture/`, `docs/operator-guide/runbooks/`, `SECURITY.md` at the repo root). No application-code changes. |
| Rule 36 — Every new FR with UX impact must be documented | ✅ Pass (CI-enforced) | T065's `scripts/check-doc-references.py` enforces FR-reference drift detection per FR-616; the script scans `docs/` for `FR-NNN` references and validates against the canonical FR document. |
| Rule 37 — Env vars / Helm values / feature flags auto-documented | ✅ Pass | T060 (env vars via `generate-env-docs.py`) + T070 (Helm values via `helm-docs`) + T078 (feature flags — manual but reviewed against the FR-584 inventory per feature 086's audit). All three have CI gates that fail PRs on drift. |
| Rule 38 — Multi-language parity enforced | ✅ Pass | T087 extends feature 088's `scripts/check-readme-parity.py` pattern to the docs tree (User-facing sections only); 7-day grace window via auto-created GitHub issue per FR-602 + the existing `docs-translation-exempt` label override. |
| FR-605 — 11 top-level sections | ✅ Pass | T100-T280 phase structure mirrors the 11 sections; the existing `docs/` files are migrated into the new structure. |
| FR-619 — API reference auto-generated | ✅ Pass | T076 fetches the OpenAPI spec via `app.openapi()` invoked from a small build script; T077 runs Redoc + Swagger UI as static-site embeds. |

**Verdict: gate passes. No declared variances. UPD-039 satisfies all four constitutional rules (29, 36, 37, 38) governing documentation.**

## Project Structure

### Documentation (this feature)

```text
specs/089-comprehensive-documentation-site/
├── plan.md                # this file
├── spec.md
├── planning-input.md
└── tasks.md               # produced by /speckit.tasks (next phase)
```

### Source Code (repository root) — files this feature creates or modifies

```text
mkdocs.yml                                   # MODIFY (extend: add 5 plugins; replace nav block per FR-605; reconcile v3/v4 → v5/v6 nav drift)
requirements-docs.txt                        # MODIFY (add 5 new pip deps)
SECURITY.md                                  # NEW at repo root per FR-618 + plan correction §5

docs/                                        # REORGANIZE per FR-605 11-section structure
├── index.md                                 # NEW (docs landing page; cross-links to README)
├── getting-started/                         # NEW directory (FR-605 §1)
│   ├── index.md
│   ├── what-is-musematic.md, quick-start.md, glossary.md, first-tutorial.md   # 4 NEW pages
├── user-guide/                              # NEW directory (FR-605 §2 — LOCALIZED into 6 locales per FR-620)
│   ├── index.md
│   ├── consumer/{discovering-agents,starting-conversation,observing-execution,reasoning-traces,alerts}.md
│   ├── creator/{registering-agent,fqn,purpose-approach,visibility-tools,packaging,certification,publishing}.md
│   ├── workspace-collaboration/{goals,multi-agent,attention,gid-correlation}.md
│   └── workbenches-overview.md
├── admin-guide/                             # NEW directory (FR-605 §3 — LOCALIZED into 6 locales)
│   ├── index.md
│   └── 10 sub-pages mirroring FR-548 through FR-557
├── operator-guide/                          # NEW directory (FR-605 §4 — English-only)
│   ├── index.md
│   ├── observability.md                     # REUSES existing `docs/operations/grafana-metrics-logs-traces.md` content
│   ├── dashboards-reference.md, incident-response.md, capacity-planning.md, backup-restore.md, multi-region-failover.md
│   ├── runbooks/                            # NEW (FR-617 — ≥ 10 runbooks)
│   │   ├── index.md
│   │   └── 10 runbook pages (platform-upgrade, db-migration-rollback, dr-restore, multi-region-failover, secret-rotation, capacity-expansion, super-admin-break-glass, incident-response, log-query-cookbook, tls-emergency-renewal)
│   └── logql-cookbook.md
├── developer-guide/                         # NEW directory (FR-605 §5 — English-only)
│   ├── index.md
│   ├── building-agents.md                   # REUSES existing `docs/agents.md` content (24 lines) per inventory
│   ├── structured-logging.md                # REUSES existing `docs/development/structured-logging.md` content
│   └── 8 more pages (agent-card-spec, contract-authoring, tool-gateway, mcp-integration, a2a-integration, sdk-usage, reasoning-primitives, evaluation-authoring, self-correction-tuning)
├── api-reference/                           # NEW directory (FR-605 §6 — English-only)
│   ├── index.md
│   ├── rest-api.md                          # Embeds Redoc + Swagger UI (FR-619)
│   ├── websocket-api.md, a2a-api.md, mcp-api.md, error-codes.md
│   └── openapi.json                         # AUTO-GENERATED by T076 build script
├── architecture/                            # NEW directory (FR-605 §7 — English-only)
│   ├── index.md
│   ├── system-architecture.md               # `git mv docs/system-architecture-v5.md` (preserves history; 2284 lines)
│   ├── software-architecture.md             # `git mv docs/software-architecture-v5.md` (1651 lines)
│   ├── bounded-contexts/                    # NEW directory (one page per BC; ~30 pages)
│   ├── data-stores.md, event-topology.md, security-trust-privacy.md, observability-architecture.md, architecture-decisions.md
├── installation/                            # NEW directory (FR-605 §8 — English-only)
│   ├── index.md
│   ├── kind.md (FR-606), k3s.md (FR-607), hetzner.md (FR-608 — flagship ~1500 lines), managed-k8s.md (FR-609), air-gapped.md
├── configuration/                           # NEW directory (FR-605 §9)
│   ├── index.md
│   ├── environment-variables.md             # AUTO-GENERATED (FR-610 by T060)
│   ├── helm-values.md                       # AUTO-GENERATED (FR-611 by T070)
│   ├── feature-flags.md (FR-612 manual), url-scheme.md (FR-613), tls-strategy.md (FR-614), networking.md
├── security/                                # NEW directory (FR-605 §10 — English-only)
│   ├── index.md, threat-model.md, compliance-mapping.md, best-practices.md, responsible-disclosure.md
├── release-notes/                           # NEW directory (FR-605 §11 — versioned)
│   ├── index.md, v1.3.0.md, changelog.md (mirrors root CHANGELOG.md)
└── assets/                                  # ALREADY ON DISK from feature 088 per inventory
    └── architecture-overview.svg            # ALREADY EXISTS — REUSED across the docs site

# REMOVED via `git mv` (history preserved):
# docs/agents.md → docs/developer-guide/building-agents.md
# docs/development/structured-logging.md → docs/developer-guide/structured-logging.md
# docs/operations/grafana-metrics-logs-traces.md → docs/operator-guide/observability.md
# docs/integrations/webhook-verification.md → docs/developer-guide/mcp-integration.md (folded)
# docs/administration/audit-and-compliance.md → docs/admin-guide/security-compliance.md
# docs/administration/integrations-and-credentials.md → docs/admin-guide/system-config.md
# docs/features/{074,075,076}.md → docs/release-notes/v1.3.0.md (folded into release notes)
# docs/system-architecture-v5.md → docs/architecture/system-architecture.md
# docs/software-architecture-v5.md → docs/architecture/software-architecture.md
# docs/functional-requirements-revised-v6.md — STAYS at this path (canonical FR document)

scripts/
├── generate-env-docs.py                     # NEW (FR-610 — AST walker over Pydantic Settings + os.getenv calls + Go os.Getenv calls)
├── check-doc-references.py                  # NEW (FR-616 FR-reference drift detection)
├── export-openapi.py                        # NEW (FR-619 — `python -c "from platform.main import app; ..."`)
├── tests/
│   ├── test_generate_env_docs.py            # NEW pytest unit tests
│   └── test_check_doc_references.py         # NEW
├── check-readme-parity.py                   # ALREADY ON DISK from feature 088 (REUSED pattern by T087)
└── open-or-update-drift-issue.sh            # ALREADY ON DISK from feature 088 (REUSED by T087 for docs drift)

deploy/helm/                                 # ANNOTATE all 16 charts with helm-docs comments per plan correction §12
└── 16 chart `values.yaml` files: platform/, observability/, runtime-controller/, kafka/, redis/, postgresql/, qdrant/, neo4j/, opensearch/, clickhouse/, minio/, control-plane/, reasoning-engine/, simulation-controller/, ui/, observability/values-{minimal,standard,enterprise,e2e}.yaml

terraform/                                   # NEW directory per plan correction §4 + research R6
├── environments/production/{main.tf,variables.tf,terraform.tfvars.example}
├── environments/dev/{main.tf,variables.tf,terraform.tfvars.example}
└── modules/hetzner-cluster/{main.tf,variables.tf,outputs.tf}

.github/workflows/
├── ci.yml                                   # MODIFY (add `docs: ['docs/**', 'mkdocs.yml']` filter; add `docs-staleness` job per FR-616)
├── docs-build.yml                           # NEW (build MkDocs on PR + deploy to GitHub Pages on push to main via `mike`)
└── docs-external-links.yml                  # ALREADY ON DISK from feature 088 (extended in T030 to scan docs tree weekly)
```

**Structure Decision**: UPD-039 builds on the existing `mkdocs.yml` config (NOT a generator switch); reorganizes the on-disk `docs/` tree into the FR-605 11-section structure via `git mv` (preserves history); creates 11 new top-level docs directories; adds 3 new auto-generation scripts at `scripts/`; modifies all 16 Helm chart `values.yaml` files with helm-docs annotations; creates the Hetzner Terraform modules at `terraform/`; creates 1 new GitHub Actions workflow (`docs-build.yml`) and modifies 1 (`ci.yml`); creates `SECURITY.md` at the repo root. No application code, no migrations, no new BC.

## Brownfield-Input Reconciliations

These are corrections from spec to plan. Each is an artifact-level discrepancy between the brownfield input and the on-disk codebase.

1. **Brownfield says "Docusaurus 3 (recommended)"; on-disk has MkDocs Material configured.** Verified per inventory: `mkdocs.yml` exists with full Material theme + 16 features + search plugin. UPD-039 EXTENDS this config (adds 5 plugins: i18n, mike, redirects, gen-files, mkdocstrings); does NOT switch to Docusaurus.

2. **`mkdocs.yml` `nav:` block references OUTDATED v3/v4 documents.** Per inventory: existing nav points at `system-architecture-v3.md`, `software-architecture-v3.md`, `functional-requirements-revised-v4.md` — but on-disk files are v5 (architecture) and v6 (FR). T020 reconciles the nav drift by replacing the nav block with the FR-605 11-section structure pointing at the new file paths from T120-T125 (`git mv` migrations).

3. **Existing `docs/` tree has only 13 .md files + 1 SVG**, not the comprehensive structure the brownfield template implies. Per inventory: `agents.md` (24 lines) + `development/structured-logging.md` + `operations/grafana-metrics-logs-traces.md` + `integrations/webhook-verification.md` + `administration/{audit-and-compliance,integrations-and-credentials}.md` + `features/{074,075,076}.md` + 3 v5/v6 architecture docs. T120-T125 `git mv` the existing files into the new FR-605 structure (preserves history); T130-T220 author the missing pages (~50 new pages for Track B, ~30 for Track C, ~10 for Track D, ~10 runbooks).

4. **Hetzner Terraform modules do NOT exist on disk.** Confirmed per inventory: NO `terraform/` directory at the repo root; NO `.tf` files anywhere. **Resolution:** UPD-039 commits Terraform modules in this feature (`terraform/environments/production/` + `terraform/modules/hetzner-cluster/`). The plan estimate (~ 20 dev-days) absorbs this; Track D's effort estimate goes from 4 to ~6 dev-days to accommodate Terraform authoring + verification.

5. **`SECURITY.md` does NOT exist at the repo root.** Confirmed per inventory. UPD-039 creates it in T080 per FR-618.

6. **OpenAPI export pipeline.** Per inventory: `apps/control-plane/src/platform/main.py` has FastAPI's `app.openapi()` configured (the routes `/api/openapi.json` and `/openapi.json` are served at runtime); NO static export at `docs/api-reference/openapi.json` exists. **Resolution:** T076 creates `scripts/export-openapi.py` — a small build-time script that imports the platform's FastAPI app via `from platform.main import app; print(json.dumps(app.openapi()))` and writes to `docs/api-reference/openapi.json`. Alternative considered (run the platform locally in CI + `curl /api/openapi.json`) — REJECTED because it requires spinning up the entire platform stack; the import-and-call approach is simpler.

7. **`requirements-docs.txt` has only 3 dependencies.** Per inventory: `mkdocs==1.6.1`, `mkdocs-material==9.5.45`, `pymdown-extensions==10.12`. UPD-039 adds 5 NEW dependencies: `mkdocs-static-i18n` (FR-620), `mike` (FR-615), `mkdocs-redirects` (preserve old paths), `mkdocs-gen-files` (FR-619/610/611), `mkdocstrings[python]` (Developer Guide inline docstrings). Note: `helm-docs` is a Go binary (NOT a Python package) — installed via `curl https://github.com/norwoodj/helm-docs/releases/download/v1.13.1/helm-docs_1.13.1_Linux_x86_64.tar.gz` in CI.

8. **NO `docs:` filter in `ci.yml`.** Per inventory: the existing `dorny/paths-filter@v3` block at lines 40-79 has filters for python / go-* / frontend / helm / migrations / proto / images / readme — but NO `docs:` filter. T030 adds a `docs: ['docs/**', 'mkdocs.yml']` filter; the new `docs-staleness` job conditionally runs on `if: needs.changes.outputs.docs == 'true'`.

9. **Translation vendor relationship.** Same vendor as feature 083 (UI strings) + feature 088 (READMEs). UPD-039 reuses; T200 verifies engagement.

10. **`docs/assets/architecture-overview.svg` already exists.** Per inventory: the SVG is on disk (committed by feature 088's T005). UPD-039 REUSES it across the Architecture section + the docs landing page.

11. **`docs/agents.md` content is small but valuable.** Per inventory: 24 lines describing model binding + certification gates. T120's `git mv` moves it to `docs/developer-guide/building-agents.md` AND extends with sections from feature 075 (model catalog) + feature 086 (admin workbench's model-catalog page).

12. **16 Helm charts × 28+ values files require helm-docs annotations.** Per inventory: NONE have annotations yet. T070's annotation work is large (~ 1.5 dev-days alone) — adds `# -- description` comments above every documented value across 16 chart `values.yaml` files. The plan estimate absorbs this.

13. **41 Pydantic Settings classes + 11 raw `os.getenv()` Python calls + 38 `os.Getenv()` Go calls.** Per inventory: env vars are partially centralized in `apps/control-plane/src/platform/common/config.py` (2405 lines, 41 Settings classes with `env_prefix`) and partially scattered. T060's `scripts/generate-env-docs.py` walks BOTH the Pydantic `BaseSettings` subclasses (via `cls.__fields__` introspection) AND the raw `os.getenv()` / `os.Getenv()` calls (via Python AST + Go AST). Output table groups by component (Settings class name) + lists scattered calls under "Other".

14. **Versioning approach.** Brownfield says "versioning aligned with platform release tags". MkDocs Material's canonical versioning is via `mike`. Plan adopts `mike` per Phase 0 research R3.

15. **`mkdocs.yml` site_url.** Per inventory: `https://gntik-ai.github.io/musematic/` — GitHub Pages. UPD-039 ships GitHub Pages first per spec correction §7; CNAME `docs.musematic.ai` → `gntik-ai.github.io` is a follow-up DNS task.

16. **The `release-notes/` section's relation to `CHANGELOG.md`.** Per inventory: `CHANGELOG.md` exists at the repo root with 1 entry under "Unreleased". T079 authors `docs/release-notes/v1.3.0.md` summarizing UPD-036 / UPD-037 / UPD-038 / UPD-039 (the v1.3.0 cohort); the root `CHANGELOG.md` is preserved unchanged AND symlinked / mirrored as `docs/release-notes/changelog.md` per FR-605 §11.

## Phase 0 — Research and Design Decisions

### R1. MkDocs Material vs. Docusaurus

**Decision**: MkDocs Material — the existing on-disk choice. Reasons: (a) `mkdocs.yml` is already configured + 16 theme features + search plugin + dark-mode palette; (b) Material is one of FR-615's named alternatives; (c) Python-based generator integrates naturally with the platform's Python ecosystem (auto-gen scripts in Python); (d) Switching to Docusaurus would require rebuilding the entire config + theme + nav.

### R2. i18n plugin choice

**Decision**: `mkdocs-static-i18n`. Reasons: (a) actively maintained; (b) MkDocs Material's official i18n recommendation; (c) supports FR-620 partial-localization (some sections English-only) via per-section `default_language` overrides; (d) language-switcher widget integrates with the Material theme's nav.

### R3. Versioning plugin choice

**Decision**: `mike`. Reasons: (a) MkDocs Material's official versioning recommendation; (b) deploys multiple versions to the `gh-pages` branch with a version selector in the UI; (c) integrates with `mkdocs-static-i18n`; (d) brownfield's "versioning aligned with platform release tags" maps directly to mike's `mike deploy --update-aliases v1.3.0 latest` pattern.

### R4. Auto-generated content via mkdocs-gen-files

The `mkdocs-gen-files` plugin runs Python scripts at build time to generate Markdown files. UPD-039 uses it for:
- The OpenAPI Swagger UI / Redoc embedding (T076 imports the OpenAPI spec from FastAPI)
- The env-vars reference table (T060 invokes `generate-env-docs.py`)
- The Helm-values reference (T070 invokes `helm-docs` via subprocess)

**Decision**: All three auto-generated artefacts are produced by `mkdocs-gen-files` hook scripts in `docs/gen_*.py` (per the plugin's convention). The generated files are committed to the repo (NOT just produced at build time) so the docs site can be reviewed in PRs without running the build.

### R5. OpenAPI export

Per plan correction §6: `apps/control-plane/src/platform/main.py` has FastAPI `app.openapi()` configured. **Decision**: Snapshot at build time. T076 implements `scripts/export-openapi.py` invoking `app.openapi()` directly; output is `docs/api-reference/openapi.json`. The script runs (a) on every PR touching `apps/control-plane/` to verify the spec is still parseable AND (b) committed to the repo so docs viewers see the latest. Output uses `json.dumps(spec, sort_keys=True, indent=2)` to ensure deterministic output (per plan.md risk-register row 10).

### R6. Hetzner Terraform module ownership

Per plan correction §4: the modules don't exist on disk. **Decision**: option (a) — commit Terraform modules in this feature. Reasons: (a) tightly coupled to the Hetzner installation guide (T240); (b) versioning the modules with the docs ensures the guide stays accurate; (c) operators self-deploying on Hetzner expect the modules to be `git clone`-able alongside the docs. Track D estimate increases from 4 to ~6 dev-days.

### R7. Documentation localization scope

FR-620 + spec correction §6: User-facing sections (Getting Started, User Guide, Admin Guide) localized into 6 locales (English, Spanish, German, French, Italian, Simplified Chinese — NOT Japanese); technical sections English-only. **Decision**: per-section configuration in `mkdocs.yml`'s `mkdocs-static-i18n` plugin block — `localized_sections: [getting-started, user-guide, admin-guide]`; all other sections inherit `default_language: en`.

### R8. CI staleness detection — three checks

Per FR-616 + Constitution Rule 37, three staleness checks fail the build:
1. **Env-var-doc drift**: `scripts/generate-env-docs.py` runs in CI; output diff against committed `docs/configuration/environment-variables.md` MUST be empty.
2. **Helm-values-doc drift**: `helm-docs` regenerates from annotated `values.yaml` files; output diff against committed `docs/configuration/helm-values.md` MUST be empty.
3. **FR-reference drift**: `scripts/check-doc-references.py` scans `docs/` for `FR-NNN` references and validates each FR exists in the canonical FR document.

**Decision**: T085 implements all three as a single `docs-staleness` CI job in `ci.yml`; each check is a separate step with its own exit code; the job fails on any non-zero exit.

### R9. `helm-docs` invocation

`helm-docs` is a Go binary that walks Helm charts and generates documentation from YAML comments. Two integration patterns:
1. **Per-chart README.md generation**: `helm-docs` writes a `README.md` next to each `values.yaml`.
2. **Aggregated documentation page**: a single `docs/configuration/helm-values.md` file lists all values across all charts.

**Decision**: BOTH. Per-chart `README.md` files (option 1) are useful for chart-level operators; the aggregated `docs/configuration/helm-values.md` (option 2) is the FR-611 contract. T070's CI step runs `helm-docs` per chart AND a small Python script aggregates the per-chart `README.md` into the unified page.

### R10. GitHub Pages deployment

The existing `mkdocs.yml` `site_url: https://gntik-ai.github.io/musematic/` indicates GitHub Pages is the target. **Decision**: T030's `docs-build.yml` workflow uses `mike deploy --update-aliases v1.3.0 latest --push` to deploy to the `gh-pages` branch. Workflow runs on push to `main` after PR merge. Per spec correction §7, migration to a Hetzner-hosted instance is a follow-up DNS task (CNAME `docs.musematic.ai` → `gntik-ai.github.io`).

### R11. Translation vendor scope expansion

UPD-039 sends User Guide + Admin Guide + Getting Started to the same vendor as features 083 + 088. The vendor's 7-day SLA per locale applies. **Decision**: T300 (translation submission) treats the vendor commission as a single batch (50+ pages × 5 locales = 250+ files); the SLA is 7 days per FR-602 + the brownfield's "Translation Management" section. Native-speaker review per locale is the human gate.

## Phase 1 — Design

### Track A — Site Infrastructure Architecture

```
                ┌─────────────────────────────────────────────────┐
                │ Existing mkdocs.yml (Material theme + search)    │
                │   ↓                                              │
                │   EXTEND with 5 plugins:                         │
                │   • mkdocs-static-i18n (FR-620)                  │
                │   • mike (FR-615 versioning)                     │
                │   • mkdocs-redirects (preserve old paths)        │
                │   • mkdocs-gen-files (FR-619/610/611 auto-gen)   │
                │   • mkdocstrings[python] (Developer Guide)       │
                │                                                  │
                │   REPLACE nav block with FR-605 11-section       │
                │   structure                                      │
                │   ↓                                              │
                │   Build via `mkdocs build` (in CI):              │
                │   • mkdocs-gen-files runs hooks:                 │
                │     - docs/gen_env_vars.py → docs/configuration/ │
                │       environment-variables.md                   │
                │     - docs/gen_helm_values.py → invokes          │
                │       helm-docs → docs/configuration/helm-values │
                │     - docs/gen_openapi.py → reads                │
                │       docs/api-reference/openapi.json (T076)     │
                │       → renders Swagger UI + Redoc embeds        │
                │   • mkdocs-redirects rewrites old paths          │
                │   • mike deploys versioned site to gh-pages      │
                └─────────────────────────────────────────────────┘
```

### Track B / C — Documentation Content Pipeline

```
1. Author canonical English content per FR-605 11 sections
   ↓
2. T060 / T070 / T076 auto-generate reference content
   (env-vars, Helm-values, OpenAPI)
   ↓
3. T087 docs-translation parity check enforces 7-day SLA
   on User-facing sections (FR-620 scope)
   ↓
4. Translation vendor (same as features 083 / 088) delivers
   localized variants for User Guide / Admin Guide / Getting Started
   ↓
5. Native-speaker review per locale (≥ 4/5 quality rating)
   ↓
6. Merge → docs-build CI → GitHub Pages deploy via mike
```

### Track D — Hetzner Installation Guide Architecture (FR-608)

The Hetzner guide is the largest single artefact. Structure per the brownfield's 10-step layout:

```
docs/installation/hetzner.md
├── Prerequisites (Hetzner account, domain, tools versions)
├── Step 1 — Provision infrastructure with Terraform
│   ├── Reference to terraform/environments/production/ (NEW per plan correction §4)
│   ├── Example tfvars
│   └── Run `terraform init && terraform apply`
├── Step 2 — kubeadm bootstrap (containerd + kubeadm init + worker join)
├── Step 3 — Core cluster addons (Cilium / MetalLB / NGINX Ingress / cert-manager / Longhorn)
├── Step 4 — DNS records (canonical app.musematic.ai / api.musematic.ai / grafana.musematic.ai per FR-613)
├── Step 5 — TLS certificates (Let's Encrypt DNS-01 wildcard per FR-614)
├── Step 6 — Observability stack (helm install observability per UPD-035)
├── Step 7 — Musematic platform (helm install platform with values-hetzner-production.yaml overlay)
├── Step 8 — Super admin bootstrap (passwordSecretRef per UPD-036 — sealed secret)
├── Step 9 — Verification checklist (login + workspace + agent + observability)
├── Step 10 — Production hardening (NetworkPolicy + backup + retention + alerting + auto-recovery + quarterly failover)
└── Troubleshooting (DNS propagation / Let's Encrypt rate limits / MetalLB IP conflicts / Longhorn PV scheduling / kubeadm cert expiry / time drift)
```

## Phase 2 — Implementation Order

| Phase | Goal | Tasks (T-numbers indicative; final list in tasks.md) | Wave | Parallelizable |
|---|---|---|---|---|
| **0. Setup** | Inventory verification, vendor engagement, plan-coordination | T001-T005 | W14.0 | yes |
| **1. Track A — Site infrastructure** | mkdocs.yml plugins, ci.yml docs filter, docs-build workflow, helm-docs install | T010-T030 | W14A.1 | mostly sequential |
| **2. Track A — Auto-gen scripts** | generate-env-docs.py, check-doc-references.py, helm-docs annotations across 16 charts | T040-T070 | W14A.2 | mostly parallel |
| **3. Track A — OpenAPI + staleness CI** | export-openapi.py + Redoc embed + docs-staleness CI job | T076-T086 | W14A.3 | sequential |
| **4. Track B — Getting Started + User Guide (English)** | Author Getting Started + User Guide canonical English content | T100-T140 | W14B | parallel sub-tasks |
| **5. Track B — Admin Guide (English)** | Author 10 admin-guide pages mirroring FR-548-557 | T150-T160 | W14B | parallel sub-tasks |
| **6. Track C — Architecture + Developer Guide** | git mv v5 architecture docs + author bounded-contexts catalog + Developer Guide | T170-T190 | W14C | mostly parallel |
| **7. Track C — API Reference + Configuration Reference + Security Guide** | Embed OpenAPI + author config refs + author Security Guide + SECURITY.md | T200-T220 | W14C | mostly parallel |
| **8. Track D — Installation Guides + Terraform modules** | Author kind / k3s / Hetzner / managed K8s guides + Terraform modules | T230-T260 | W14D | mostly parallel |
| **9. Track D — Runbook library** | Author 10 runbooks per FR-617 | T270-T280 | W14D | parallel (10 runbooks) |
| **10. Translation + native review** | Submit User-facing sections to vendor; per-locale native review | T300-T320 | W14E | parallel (5 locales) |
| **11. Verification + deploy** | End-to-end verification of each installation guide; GitHub Pages deploy | T330-T345 | W14F | sequential |
| **12. Polish + cross-feature coord** | Final cross-review (product + engineering + compliance); CLAUDE.md update | T350-T360 | W14G | yes |

### Wave layout

UPD-039 lands in **Wave 14** (last feature in the v1.3.0 audit-pass cohort). Sub-divisions:

- **W14.0 — Setup**: T001-T005; ~0.25 dev-day; one engineer.
- **W14A — Site infrastructure**: T010-T086; ~3.5 dev-days; one engineer (mostly sequential auto-gen tooling).
- **W14B — User-facing docs**: T100-T160; ~5 dev-days; 2 writers (parallel sub-tasks across pages).
- **W14C — Technical docs**: T170-T220; ~3.5 dev-days; 1 writer.
- **W14D — Installation guides + runbooks**: T230-T280; ~6 dev-days (Hetzner alone is ~3 days including Terraform modules); 1 ops-background engineer.
- **W14E — Translation**: T300-T320; ~0.5 dev-day internal + 7-day vendor SLA wall-clock.
- **W14F — Verification**: T330-T345; ~1 dev-day (Hetzner end-to-end verification on a live deployment).
- **W14G — Polish**: T350-T360; ~0.5 dev-day.

**Total internal effort: ~20 dev-days** (above the brownfield's 15-day estimate due to Terraform modules per plan correction §4 + 16 Helm charts requiring annotation per plan correction §12). Wall-clock with 3 writers + 1 engineer + vendor SLA: **~10-12 days** from kickoff.

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Content sprawl** — docs grow faster than maintained | High | Medium | Strict per-page ownership; T085 staleness checks block PR merges on drift; quarterly documentation review cadence. |
| **Translation drift** — English updates outpace translation refresh | Medium | Medium | T087 extends feature 088's parity-check pattern to the docs tree; 7-day grace window per FR-602; vendor budget allocated per quarter. |
| **Hetzner installation guide regression** — infrastructure changes break documented commands | Medium | High | T340 quarterly validation against fresh Hetzner deployment; T260 Terraform modules versioned with the docs; CI integration test renders the Terraform modules on every PR touching `terraform/`. |
| **Auto-generation drift** — code changes without running scripts | Medium | High | T085's three CI staleness checks fail the build on any drift; commit diffs are part of the PR. |
| **External link rot** — Hetzner / Let's Encrypt / cloud-provider URLs change | Medium | Low | feature 088's `docs-external-links.yml` weekly workflow extended in T030 to scan `docs/` external links. |
| **Localization quality** — auto-translated segments slip through review | Medium | Medium | T320 mandates native-speaker review per locale; vendor's 7-day SLA per FR-602; T087 enforces structural parity. |
| **MkDocs build flakiness** — plugin interactions break the build | Low | Medium | T030 ships unit tests for the auto-gen scripts; T020 verifies plugin compatibility on a fresh install. |
| **`helm-docs` Go binary install fails in CI** | Low | Medium | T015 pinned-version download via `curl https://github.com/norwoodj/helm-docs/releases/download/v1.13.1/...`; checksum verified per plan correction §7. |
| **`mike` versioning conflicts with `mkdocs-static-i18n`** | Low | Medium | T020 verifies plugin compatibility on a fresh install; documented order: `mkdocs-static-i18n` first, `mike` second per the plugin's interoperability docs. |
| **OpenAPI snapshot drift** — `app.openapi()` output changes across runs (e.g., due to dict ordering) | Low | Low | T076's `export-openapi.py` uses `json.dumps(spec, sort_keys=True, indent=2)` to ensure deterministic output; T085's CI step diffs against committed snapshot. |
| **Terraform modules' Hetzner provider version drift** | Medium | Medium | T260's modules pin the Hetzner provider version; T340 quarterly validation catches drift. |
| **Cross-feature coordination — feature 086's admin workbench pages** | Medium | Medium | T160's Admin Guide pages mirror feature 086's `/admin/...` routes; if 086 hasn't landed at the time UPD-039 starts, the Admin Guide ships placeholder pages with TODO markers. |
| **`SECURITY.md` PGP key generation** | Low | Low | T080 uses an existing organization PGP key OR generates a fresh key; the public key is published at `https://musematic.ai/.well-known/security.txt` per the brownfield's security note. |
| **`docs/agents.md` migration loses content** | Low | Low | T120's `git mv` preserves history; T180 extends the migrated file with feature 075 (model catalog) + feature 086 (admin workbench) cross-references. |

## Open Questions

- **Q1**: Should the docs site host on `docs.musematic.ai` (Hetzner instance) OR stay on GitHub Pages? **Working assumption**: GitHub Pages first per spec correction §7; CNAME migration is a follow-up DNS task.
- **Q2**: Should the API Reference embed Swagger UI OR Redoc OR both? **Working assumption**: BOTH per the brownfield input + FR-619 acceptance criteria; Redoc as the canonical view + Swagger UI for "Try it out" interactive testing.
- **Q3**: Should the runbook library be searchable separately from the rest of the docs site? **Working assumption**: NO — the unified MkDocs Material search is sufficient; runbook titles include keyword prefixes (e.g., "Runbook: Disaster Recovery Restore") to surface in search results.
- **Q4**: Should the User Guide's localized variants be in separate top-level directories (`docs/es/user-guide/...`) OR per-file translations (`docs/user-guide/index.es.md`)? **Working assumption**: per-file translations via `mkdocs-static-i18n`'s default convention.
- **Q5**: Should `mike` deploy each version to a separate URL path OR replace the latest? **Working assumption**: `mike deploy --update-aliases v1.3.0 latest` deploys to `/v1.3.0/` AND aliases `latest` to it; older versions remain at their version paths.
- **Q6**: Should the Terraform modules be tested in CI? **Working assumption**: T260's modules are tested via `terraform validate` + `terraform plan` (NOT `terraform apply` — too expensive); T340's quarterly validation runs the full `terraform apply` against a real Hetzner test account.
- **Q7**: Should the FR-617 runbook library be linked from the platform's incident-response BC (feature 080 / UPD-031)? **Working assumption**: YES — the incident-response dashboard's "View runbook" link deep-links into `docs.musematic.ai/operator-guide/runbooks/{slug}`; feature 080 owns the deep-link rendering, UPD-039 owns the runbook content.

## Cross-Feature Coordination

| Feature | What we need from them | Owner action | Blocking? |
|---|---|---|---|
| **083 / UPD-030 (Accessibility & i18n)** | Translation vendor relationship + 7-day SLA workflow + axe-core CI gate | Already established | No |
| **085 / UPD-035 (Observability + Helm bundle)** | Observability install via `helm install observability` + 22 dashboards + `platform-cli observability` CLI | Already on disk; T240 (Hetzner guide step 6) references | No |
| **086 / UPD-036 (Admin Workbench)** | `/admin/...` route enumeration for the Admin Guide | Pending — UPD-036 lands first | Yes (Track B Phase 5 — Admin Guide pages) |
| **087 / UPD-037 (Public Signup Flow)** | Signup + OAuth flow user-facing pages for the User Guide | Pending — UPD-037 lands first | Yes (Track B Phase 4 — User Guide pages) |
| **088 / UPD-038 (Multilingual README)** | `docs/assets/architecture-overview.svg` + the 6 README files at the repo root | Already on disk per inventory; T010 reuses; T120 cross-links | No |
| **080 / UPD-031 (Incident Response)** | Incident-response dashboard "View runbook" deep-link rendering | Pending — feature 080's scope; T270 ships the runbook content | No (UPD-039's runbooks land independently) |
| **CI / GitHub Pages infrastructure** | `gh-pages` branch + `peaceiris/actions-gh-pages@v3` action OR `mike deploy --push` | Already available | No |

## Phase Gate

**Plan ready for `/speckit.tasks` when**:
- ✅ Constitutional anchors enumerated and gate verdicts recorded
- ✅ Brownfield-input reconciliations enumerated (16 items)
- ✅ Research decisions R1-R11 documented
- ✅ Wave placement (W14.0/A/B/C/D/E/F/G) confirmed
- ✅ Cross-feature coordination matrix populated
- ✅ Risk register populated with mitigations
- ✅ Open questions enumerated (none blocking)

The plan is ready. The next phase (`/speckit.tasks`) breaks the 12-phase implementation order above into ordered, dependency-annotated tasks (T001-T360, indicative).

## Complexity Tracking

> **Filled when Constitution Check has violations that must be justified.**

| Variance | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| **MkDocs Material vs. Docusaurus per spec correction §1** | The brownfield recommended Docusaurus, but the on-disk `mkdocs.yml` already has Material configured | Switching generators would require rebuilding the entire config + theme + nav — pure waste |
| **`helm-docs` is a Go binary, NOT a Python package** | Python wrappers around helm-docs don't exist; the Go binary is the canonical tool | Re-implementing helm-docs in Python would be a ~500-line new tool to maintain — disproportionate |
| **Terraform modules committed in this feature per plan correction §4 + R6** | The brownfield assumes "modules from the user's prior work" that don't exist on disk; the Hetzner guide depends on them | Referencing an external Terraform module repo would break the docs ↔ infrastructure version coupling |
| **20 dev-days vs. brownfield's 15** | Terraform modules + 16 Helm chart annotations + 41 Pydantic Settings + 38 Go env vars + 10 runbooks add ~5 days | Underestimating risks the feature shipping incomplete |
| **Mike versioning vs. mkdocs-versioning** | `mike` is the Material-recommended versioning plugin | `mkdocs-versioning` is older and less maintained |
| **Per-section i18n config (some English-only, some localized)** | FR-620 explicitly mandates partial localization | Localizing all sections (including Architecture / API Reference) would 6× the translation cost for low audience benefit |
