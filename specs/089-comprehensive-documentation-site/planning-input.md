# Planning Input — UPD-039 Comprehensive Documentation Site and Installation Guides

> **Captured verbatim from the user's `/speckit.specify` invocation on 2026-04-27.** This file is the immutable record of the brownfield context that authored spec.md. Edits MUST NOT be made here; if a correction is needed, edit spec.md and append a note to the corrections list at the top of this file.

## Corrections Applied During Spec Authoring

1. **MkDocs Material, NOT Docusaurus.** Brownfield recommends Docusaurus 3; on-disk `mkdocs.yml` confirms MkDocs Material is already configured. UPD-039 extends the existing config.
2. **FR document is v6, architecture docs are v5** (NOT v5/v4 as the brownfield states). Verified per feature 088 inventory: `functional-requirements-revised-v6.md`, `software-architecture-v5.md`, `system-architecture-v5.md`.
3. **`docs/` tree reorganization.** On-disk subdirectories `administration/`, `development/`, `features/`, `integrations/`, `operations/` do NOT match FR-605's 11-section structure. UPD-039 reorganizes via `git mv` + `mkdocs-redirects` for backwards compat.
4. **Hetzner Terraform modules do NOT exist on disk.** No `terraform/` directory at repo root. The modules are EITHER committed in this feature OR referenced as an external repo; plan phase decides.
5. **`SECURITY.md` does NOT exist at repo root.** UPD-039 creates it per FR-618.
6. **6 locales (FR-620), NOT 7.** UI strings include `ja` (feature 083 added it out-of-spec); docs follow FR-620's 6 (English, Spanish, Italian, German, French, Simplified Chinese).
7. **Site URL.** On-disk `mkdocs.yml` has `site_url: https://gntik-ai.github.io/musematic/`; brownfield proposes `docs.musematic.ai`. UPD-039 ships GitHub Pages first + adds CNAME as a follow-up DNS task.
8. **Architecture diagram** — UPD-038's `docs/assets/architecture-overview.svg` is REUSED.
9. **Search** — MkDocs Material built-in (already enabled in `mkdocs.yml`); Algolia is a follow-up.
10. **`scripts/generate-env-docs.py` is NEW.** No equivalent exists.
11. **`helm-docs`** is a NEW dev-tool dependency (CI-only).
12. **Pages by URL** (`app.musematic.ai`, `api.musematic.ai`, `grafana.musematic.ai`) are documented but not enforced at the platform layer.

---

# UPD-039 — Comprehensive Documentation Site and Installation Guides

## Brownfield Context

**Current state (verified in repo):**
- `docs/` folder contains only three technical specs: `functional-requirements-revised-v5.md`, `software-architecture-v4.md`, `system-architecture-v4.md`.
- No user-facing documentation for operators, administrators, developers, or end users.
- No installation guides (kind, k3s, Hetzner, managed K8s).
- No configuration reference (environment variables, Helm values, feature flags).
- No API reference as a browsable site (OpenAPI is served from the running platform per FR-497, but not documented at rest).
- No security disclosure policy (`SECURITY.md`).
- No published URL and domain scheme.
- No published TLS certificate strategy.
- Existing Terraform modules for Hetzner-based Kubernetes deployment exist (from the user's memory context); these need to be documented end-to-end alongside the Helm charts.

**FRs:** FR-605 through FR-620 (section 112).

---

## Summary

UPD-039 converts the repository's documentation from three technical specs into a comprehensive documentation site covering all user roles (consumer, creator, admin, super admin, operator, developer) and all deployment scenarios (local dev on kind, single-node k3s, production on Hetzner Cloud with load balancer, managed Kubernetes on GKE / EKS / AKS). The documentation is built with a static-site generator, auto-generated where possible (API reference, env var reference, Helm values reference), localized where the audience warrants it (user-facing sections only), and kept in sync with code via CI staleness checks.

The feature includes concrete installation playbooks tied to the documented URL scheme:
- Dev environment: `dev.musematic.ai`, `dev.api.musematic.ai`, `dev.grafana.musematic.ai`
- Production environment: `app.musematic.ai`, `api.musematic.ai`, `grafana.musematic.ai`

---

## User Scenarios

### User Story 1 — Operator installs Musematic on Hetzner for the first time (Priority: P1)

(See spec.md User Story 1 — captured verbatim per the brownfield input.)

### User Story 2 — Developer consults API reference (Priority: P1)

(See spec.md User Story 2.)

### User Story 3 — Super admin consults environment variables reference (Priority: P1)

(See spec.md User Story 3.)

### User Story 4 — Native Spanish-speaking user reads User Guide (Priority: P2)

(See spec.md User Story 4.)

### User Story 5 — Operator responds to incident using runbook library (Priority: P1)

(See spec.md User Story 5.)

---

## Edge Cases

- **FR reference drift**: PR renames or renumbers a FR; documentation references become stale. CI detects and blocks merge until resolved.
- **Env var added in code without documentation update**: `generate-env-docs.py` reads code and outputs a canonical list; CI diff against committed Configuration Reference.
- **Helm value renamed**: `helm-docs` regenerates from YAML comments; PR check fails if regenerated output differs from committed docs.
- **Documentation site build failure**: CI fails the PR with actionable error.
- **External link rot**: weekly scheduled link checker opens an issue with broken links.
- **Localized screenshot drift from UI changes**: screenshot QA checklist added to translation vendor workflow.

---

## Documentation Site Architecture

### Technology

- **Static site generator**: Docusaurus 3 (recommended — has built-in i18n, versioning, search integration, React components in MDX).
- **Hosting**: GitHub Pages or a dedicated Hetzner instance behind `docs.musematic.ai`.
- **Search**: Algolia DocSearch (free for open-source) or Docusaurus's local search plugin.
- **API reference**: embed Redoc (static generation from OpenAPI 3.1 spec exported from running platform).
- **Auto-generation tools**: `helm-docs` for Helm values, `scripts/generate-env-docs.py` for env vars (custom AST-walker over Python and Go code).

### Site Structure

```
docs.musematic.ai/
├── Getting Started
├── User Guide                              # Localized into 6 languages
├── Administrator Guide                     # Localized into 6 languages
├── Operator Guide                          # English
├── Developer Guide                         # English
├── API Reference                           # English, auto-generated
├── Architecture                            # English
├── Installation Guides
├── Configuration Reference
├── Security Guide                          # English
└── Release Notes                           # Versioned
```

(Full nested structure per the brownfield input — see brownfield input for the per-section enumeration.)

---

## Installation Guide: Hetzner with Load Balancer

(Detailed brownfield specification covered in spec.md User Story 1 + FR-608 mapping. The Hetzner guide includes 10 sequential steps: prerequisites, Terraform provisioning, kubeadm bootstrap, core cluster addons, DNS records, TLS certificates, observability stack, Musematic platform, super admin bootstrap, verification, production hardening, troubleshooting.)

---

## Auto-Generated Documentation Tooling

### `scripts/generate-env-docs.py`

AST walker over:
- Python codebase: `os.getenv(...)` calls in `apps/control-plane/src/platform/`
- Go codebase: `os.Getenv(...)` calls in `services/*/`
- Helm templates: references to `{{ .Values... }}` and `valueFrom: env:` in `deploy/helm/`

Produces:
- `docs/configuration/environment-variables.md` with table of every variable, default, description, security classification (inferred from variable name heuristics — `PASSWORD`, `SECRET`, `TOKEN`, `KEY` → classified as sensitive).

CI runs the script and fails if committed docs don't match generated output.

### `helm-docs` integration

Every Helm values file annotated with comments in `helm-docs` format. Regeneration via `helm-docs --chart-search-root=deploy/helm --template-files=README.md.gotmpl`.

### `scripts/check-doc-references.py`

Scans `docs/` for FR references and validates:
- Every referenced FR exists in the current FR document.
- Removed FRs produce warnings so docs stay current.
- New FRs without doc coverage produce warnings (not hard failures — coverage is encouraged but not mandatory).

---

## Acceptance Criteria

- [ ] Documentation site deployed at `docs.musematic.ai` (or GitHub Pages initially)
- [ ] Site contains all sections listed in FR-605
- [ ] Localized User Guide in 6 languages
- [ ] kind installation guide (FR-606) — verified end-to-end
- [ ] k3s installation guide (FR-607) — verified end-to-end
- [ ] Hetzner installation guide (FR-608) — verified end-to-end on a live Hetzner deployment
- [ ] Managed K8s installation guide (FR-609) — verified on at least one of GKE / EKS / AKS
- [ ] Environment variables reference auto-generated (FR-610)
- [ ] Helm values reference auto-generated (FR-611)
- [ ] Feature flag reference complete (FR-612)
- [ ] URL and domain scheme documented (FR-613)
- [ ] TLS strategy documented (FR-614)
- [ ] CI checks for FR reference drift and env var/Helm docs drift (FR-616)
- [ ] Runbook library with 10+ runbooks (FR-617)
- [ ] Security guide with threat model and disclosure policy (FR-618)
- [ ] Interactive API reference with code samples (FR-619)
- [ ] Language toggle works across localized sections (FR-620)
- [ ] `SECURITY.md` at repo root with responsible disclosure policy
- [ ] Documentation landing page complete and cross-linked with README
