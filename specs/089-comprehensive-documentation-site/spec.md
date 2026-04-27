# Feature Specification: Comprehensive Documentation Site and Installation Guides

**Feature Branch**: `089-comprehensive-documentation-site`
**Created**: 2026-04-27
**Status**: Draft
**Input**: User description: "Convert the repo's three technical specs into a comprehensive documentation site (Getting Started + User Guide + Administrator Guide + Operator Guide + Developer Guide + API Reference + Architecture + Installation Guides + Configuration Reference + Security Guide + Release Notes per FR-605) using the existing on-disk MkDocs Material substrate (`mkdocs.yml` already wired). Localized User / Admin Guides in 6 languages per FR-620 + UPD-030/038. Auto-generated env vars reference (`scripts/generate-env-docs.py`), Helm values reference (`helm-docs`), feature-flag reference. Four installation guides — kind / k3s / Hetzner with LB / managed K8s — with the flagship Hetzner guide covering Terraform + kubeadm + cert-manager + Let's Encrypt DNS-01 wildcard + the canonical URL scheme `app.musematic.ai` / `api.musematic.ai` / `grafana.musematic.ai` for production and `dev.*.musematic.ai` for dev. Runbook library covering at least 10 scenarios per FR-617. Security Guide + `SECURITY.md` at repo root per FR-618. Interactive API reference with code samples in Python / Go / TypeScript / curl per FR-619. CI staleness checks for FR drift, env-var-doc drift, Helm-values-doc drift per FR-616."

> **Constitutional anchor:** This feature IS the constitutionally-named **UPD-039** ("Comprehensive Documentation Site and Installation Guides") declared in Constitution line 8 (audit-pass roster — alongside UPD-038). The feature delivers FR-605 through FR-620 (Section 112 of the FR document, lines 2241-2317). Constitutional ties: FR-488 (WCAG AA — every doc page passes axe-core, inherited from feature 083 / UPD-030), FR-489 (i18n — User / Admin Guides in 6 locales, inherited from feature 083), FR-490 (theming — dark mode for the doc site per FR-615), FR-526 (axe-core CI gate — extended to docs.musematic.ai), FR-497 (OpenAPI 3.1 spec served from the running platform — UPD-039 EMBEDS the spec via Redoc per FR-619), FR-579 (super admin break-glass — documented in the Operator Guide runbook library per FR-617), FR-617 (the runbook library inventory), FR-620 (localization policy — user-facing docs localized, technical docs English-only).

> **Scope discipline:** This feature builds on, but does NOT re-implement, the artifacts owned by:
> - **Existing `mkdocs.yml` at the repo root** — verified per inventory: MkDocs Material is already configured with `site_url: https://gntik-ai.github.io/musematic/`, repo URL, theme, navigation tabs / sections, search, code-copy, dark-mode palette toggle. UPD-039 EXTENDS this config (adds nav structure, plugins, i18n) — does NOT switch to a different generator (Docusaurus / Hugo / etc.) per spec correction §1.
> - **Existing `docs/` tree** — the on-disk subdirectories `administration/`, `development/`, `features/`, `integrations/`, `operations/` PLUS the four top-level files (`agents.md`, `functional-requirements-revised-v6.md`, `software-architecture-v5.md`, `system-architecture-v5.md`) per feature 088 inventory. UPD-039 REORGANIZES this tree per FR-605's 11-section structure (Getting Started / User Guide / Admin Guide / Operator Guide / Developer Guide / API Reference / Architecture / Installation Guides / Configuration Reference / Security Guide / Release Notes) — the existing files are MOVED into the new structure (NOT deleted; `git mv` preserves history).
> - **Feature 088 (UPD-038 — Multilingual README)** — UPD-038 owns the 6 README files at the repo root + the `docs/assets/architecture-overview.svg` shared diagram. UPD-039's docs landing page LINKS to the README; the architecture diagram is REUSED across the doc site's Architecture section per FR-603.
> - **Feature 083 (UPD-030 — Accessibility & i18n)** — UPD-039 inherits the next-intl + axe-core CI gate (per FR-488 + FR-489) AND the 7-locale catalog discipline (en, es, de, fr, it, zh-CN, ja per feature 087's verified inventory — note: NOT 6 as the brownfield states; the docs site supports the 7 catalogs that exist on disk, with `ja` treated as the same out-of-spec extra locale that was added to feature 083's UI catalogs).
> - **Feature 086 (UPD-036 — Admin Workbench)** — UPD-039 documents every admin workbench page in the Administrator Guide section, but the workbench pages themselves are owned by UPD-036.
> - **Feature 085 (UPD-035 — Extended E2E + Observability Helm Bundle)** — UPD-039 documents the umbrella chart's 3 sizing presets (`minimal` / `standard` / `enterprise`) + the `platform-cli observability install|upgrade|uninstall|status` subcommands, but the chart + CLI are owned by UPD-035.
> - **Feature 087 (UPD-037 — Public Signup Flow)** — UPD-039 documents the signup + OAuth flows in the User Guide; the flows themselves are owned by UPD-037.
> - **Existing OpenAPI 3.1 spec served by the platform** (per FR-497) — UPD-039 EMBEDS the spec into the API Reference section via Redoc per FR-619; the spec generation is owned by feature 015 (Next.js scaffold + FastAPI's OpenAPI export).

> **Brownfield-input reconciliations** (full detail captured in planning-input.md and re-verified during the plan phase):
> 1. **Documentation site technology — MkDocs Material, NOT Docusaurus.** The brownfield input recommends "Docusaurus 3 (recommended — has built-in i18n, versioning, search integration)"; the on-disk verification confirms `mkdocs.yml` already exists with MkDocs Material configured + planned site URL `https://gntik-ai.github.io/musematic/`. **Resolution:** UPD-039 EXTENDS the existing MkDocs Material config (adds the `mkdocs-material` i18n plugin OR equivalent + navigation + the `mkdocstrings` plugin for code references); does NOT switch to Docusaurus. FR-615 explicitly lists "Docusaurus, MkDocs Material, or equivalent" — MkDocs Material is the on-disk choice and is honoured.
> 2. **Existing FR document is v6, not v5.** The brownfield input writes "`functional-requirements-revised-v5.md`, `software-architecture-v4.md`, `system-architecture-v4.md`"; the on-disk reality (verified per feature 088 inventory) is `functional-requirements-revised-v6.md`, `software-architecture-v5.md`, `system-architecture-v5.md`. **Resolution:** UPD-039 references the v6 / v5 / v5 versions. The brownfield's older version numbers are stale.
> 3. **`docs/` tree reorganization.** The on-disk tree has subdirectories `administration/`, `development/`, `features/`, `integrations/`, `operations/` — these do NOT match FR-605's 11-section structure. **Resolution:** UPD-039 REORGANIZES via `git mv` to preserve history. New top-level structure: `getting-started/`, `user-guide/`, `admin-guide/`, `operator-guide/`, `developer-guide/`, `api-reference/`, `architecture/`, `installation/`, `configuration/`, `security/`, `release-notes/`. The existing content under `administration/`, `development/`, etc. is moved into the new structure (e.g., `administration/` → `admin-guide/`, `development/` → `developer-guide/`, `operations/` → `operator-guide/`). Old paths receive Markdown redirects (`mkdocs-redirects` plugin) to prevent link rot during the transition.
> 4. **Hetzner Terraform modules do NOT exist on disk.** The brownfield input writes "Existing Terraform modules for Hetzner-based Kubernetes deployment exist (from the user's memory context)"; the on-disk verification confirms NO `terraform/` directory at the repo root (exit code 2 from `ls terraform`). **Resolution:** the FR-608 Hetzner installation guide REFERENCES a Terraform module location at `terraform/environments/production/` and `terraform/modules/hetzner-cluster/` per the brownfield's example tfvars; these directories MUST exist by the time the guide is verified end-to-end. UPD-039's scope is the documentation; the Terraform modules themselves are EITHER (a) committed to the repo by a separate operator-driven task before UPD-039 ships OR (b) referenced as an external reusable module (e.g., a separate GitHub repo `gntik-ai/musematic-terraform-hetzner`). The plan phase chooses the path; the spec captures the requirement that the modules MUST exist before T071 (Hetzner install verification).
> 5. **`SECURITY.md` does NOT exist at the repo root.** Verified per feature 088 inventory. UPD-039's FR-618 contract requires `SECURITY.md` with responsible-disclosure policy + PGP key + security contact email. **Resolution:** UPD-039 creates `SECURITY.md` at the repo root in this feature.
> 6. **Locale count: 7 catalogs on disk, brownfield says "six languages".** Per feature 088's inventory + plan correction §1, the existing `apps/web/messages/` has 7 catalogs (en, es, de, fr, it, zh-CN, AND ja). FR-620 says "six supported languages (English, Spanish, Italian, German, French, Simplified Chinese)" — but feature 083 added `ja.json` out-of-spec. **Resolution:** UPD-039 follows the FR-620 6-locale list for the docs site (the official supported set); `ja` is NOT included in the docs translation scope (different from the README, where the 7th locale `ja` IS in the catalog because it's tied to the UI strings). If `ja` is later promoted to a supported locale, UPD-039's docs translation scope expands accordingly — out of scope for this feature.
> 7. **Site URL.** The on-disk `mkdocs.yml` has `site_url: https://gntik-ai.github.io/musematic/` (GitHub Pages). The brownfield input proposes `docs.musematic.ai` (Hetzner Hetzner instance). **Resolution:** UPD-039 ships on GitHub Pages first (the existing config) AND adds a CNAME / DNS record so `docs.musematic.ai` resolves to the GitHub Pages site (`gntik-ai.github.io`). Migration to a Hetzner-hosted instance is a follow-up infrastructure task, NOT part of UPD-039.
> 8. **`docs/assets/architecture-overview.svg` ownership.** The brownfield writes "Architecture diagrams remain English-labeled and shared across languages" — this is feature 088 / UPD-038's contract. **Resolution:** UPD-039 REUSES the diagram from UPD-038; does not re-create. If UPD-038 has not landed yet, UPD-039's Architecture section uses an inline ASCII description as a fallback per UPD-038's plan correction §4.
> 9. **Search technology.** The brownfield mentions "Algolia DocSearch (free for open-source) or Docusaurus's local search plugin"; MkDocs Material has a built-in client-side search plugin (verified per `mkdocs.yml` `theme.features` includes `search.highlight`, `search.share`, `search.suggest`). **Resolution:** UPD-039 uses the built-in MkDocs Material search initially; Algolia DocSearch is a follow-up enhancement after the docs hit a discoverability scale that justifies the application.
> 10. **`scripts/generate-env-docs.py` is new.** No equivalent script exists on disk. UPD-039 creates it; it walks the Python control plane code (`apps/control-plane/src/platform/`) for `os.getenv(...)` calls + the Go satellite code (`services/*/`) for `os.Getenv(...)` calls + the Helm templates (`deploy/helm/`) for `valueFrom: env:` references; produces a canonical Markdown table.
> 11. **`helm-docs` is a new dependency.** The brownfield input proposes the `helm-docs` tool for Helm values reference auto-generation. The on-disk inventory confirms NO existing helm-docs invocation. UPD-039 adds it as a CI-only dev tool (NOT a runtime dependency) — installed in the docs-build CI workflow step.
> 12. **Pages mentioned by URL but not yet defined.** The brownfield has explicit URLs (`https://app.musematic.ai`, `https://api.musematic.ai`, `https://grafana.musematic.ai`); these are FR-613's canonical URL scheme. UPD-039 documents these but does NOT enforce them at the platform layer (the platform's URL routing is owned by feature 086's admin workbench + feature 015's Next.js scaffold).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Operator Installs Musematic on Hetzner for the First Time (Priority: P1)

A platform operator has a fresh Hetzner Cloud account, a domain (`musematic.ai`) with DNS management, and an SSH key. They MUST be able to follow the FR-608 Hetzner installation guide end-to-end and reach a working production deployment in 2-3 hours. The guide covers: prerequisites, Terraform infrastructure provisioning (1 control plane + 3 worker dedicated servers + private network + firewall + Hetzner Cloud LB), kubeadm bootstrap with containerd, MetalLB + NGINX Ingress + cert-manager + Let's Encrypt DNS-01 wildcard + Longhorn, observability Helm install (per UPD-035), platform Helm install with `values-hetzner-production.yaml`, DNS records (A/AAAA for `app.musematic.ai`, `api.musematic.ai`, `grafana.musematic.ai` per FR-613), super admin bootstrap via `passwordSecretRef` (per UPD-036), post-install verification checklist, troubleshooting section.

**Why this priority**: The Hetzner installation guide is the flagship production-deployment story for self-hosted customers. P1 because (a) FR-608's enumeration is the canonical contract; (b) without it, customers self-deploying on Hetzner are blocked; (c) the guide IS the executable evidence that the platform's documented deployment topology actually works.

**Independent Test**: A operator with a fresh Hetzner account follows the guide step-by-step from a clean machine; verifies (a) Terraform provisioning completes within 30 minutes; (b) kubeadm bootstrap completes within 20 minutes; (c) addons install (MetalLB, NGINX, cert-manager, Longhorn) within 15 minutes; (d) observability + platform Helm installs complete within 30 minutes; (e) DNS propagation + TLS issuance complete within 30 minutes; (f) `https://app.musematic.ai` loads the login page; (g) super admin login succeeds; (h) `platform-cli observability status` returns green; (i) test agent execution succeeds. Total wall-clock: ≤ 3 hours including DNS propagation. The guide includes a troubleshooting section covering the documented common errors (DNS propagation delays, Let's Encrypt rate limits, MetalLB/Hetzner LB IP conflicts, Longhorn PV scheduling issues, kubeadm certificate expiry, time drift on worker nodes).

**Acceptance Scenarios**:

1. **Given** a fresh Hetzner Cloud account + a domain + an SSH key, **When** the operator follows the FR-608 guide, **Then** the platform reaches a working state in ≤ 3 hours with the canonical URL scheme honoured.
2. **Given** the Terraform modules are missing on disk per plan correction §4, **When** the operator runs `terraform init`, **Then** the guide either (a) points to the external module source OR (b) the modules are present in the repo by the time the guide is verified end-to-end.
3. **Given** the operator's domain has CAA records preventing Let's Encrypt issuance, **When** cert-manager attempts the DNS-01 challenge, **Then** the guide's troubleshooting section's "DNS propagation delays / Let's Encrypt rate limits / CAA records" entry surfaces the fix.
4. **Given** Longhorn fails to schedule a PV, **When** the operator hits the issue, **Then** the troubleshooting section's "Longhorn PV scheduling issues" entry walks through the fix.
5. **Given** the operator deploys the dev environment first (`dev.musematic.ai` etc.), **When** they later deploy production (`app.musematic.ai`), **Then** the cookie-domain separation per FR-613 prevents dev sessions from leaking into production.

---

### User Story 2 - Developer Consults the API Reference (Priority: P1)

A developer integrating with the platform needs to understand the API surface. They navigate to the API Reference section of the docs site; find any endpoint via search (the FR-615 search functionality); read its specification (FR-619 — interactive Swagger UI or Redoc); copy a working code sample (Python / Go / TypeScript / curl per FR-619); send the request against a local dev instance; get a successful response. The error code catalog (FR-619) is browseable and links from each endpoint's possible error responses to the catalog entry with remediation suggestions.

**Why this priority**: The API reference is the canonical surface for platform integrators. P1 because (a) FR-619's enumeration is the canonical contract; (b) every external integrator depends on the API reference; (c) the auto-generated nature (from the OpenAPI 3.1 spec per FR-497) ensures it stays in sync with the running platform — a stale API reference is worse than no API reference.

**Independent Test**: Open the docs site at `/api-reference/`; verify (a) the Swagger UI / Redoc renders the OpenAPI 3.1 spec; (b) the search bar finds endpoints by path / method / tag; (c) every endpoint has code samples in 4 languages (Python, Go, TypeScript, curl); (d) the "Try it out" feature works against a running platform instance (configurable base URL); (e) authentication is documented with a working example; (f) the rate-limit table per endpoint matches FR-588's stricter signup limits + the standard limits for other endpoints; (g) the error code catalog covers ≥ 50 documented error codes with remediation suggestions per FR-583's error-shape contract; (h) the API changelog covers per-version backward-compatibility annotations.

**Acceptance Scenarios**:

1. **Given** the platform is running locally, **When** the developer opens the docs site's API Reference and clicks "Try it out" for any endpoint, **Then** the request fires against the local platform with the developer's auth token and returns the documented response shape.
2. **Given** a developer searches for "register", **When** the search results render, **Then** `/api/v1/accounts/register` is the top result with its signup-flow context.
3. **Given** an endpoint returns HTTP 429, **When** the developer clicks the 429 entry in the API reference, **Then** the error-code catalog page renders with the rate-limit-exceeded explanation + the FR-588 thresholds + the `Retry-After` header semantics.
4. **Given** the OpenAPI 3.1 spec changes (new endpoint added or schema changed), **When** the docs CI runs, **Then** the API Reference auto-regenerates and the docs PR is updated; no manual sync is required.

---

### User Story 3 - Super Admin Consults Environment Variables Reference (Priority: P1)

A super admin needs to know every environment variable that affects platform bootstrap and runtime — including security classifications. They navigate to the docs site's Configuration Reference > Environment Variables page (FR-610). The page is a table with: variable name, component (control-plane / runtime-controller / web / etc.), required/optional, default value, description, security sensitivity (sensitive | configuration | informational). The table is **machine-generated** from the codebase via `scripts/generate-env-docs.py` to prevent drift per FR-610. Variables are linked to (a) the Helm values that set them by default, (b) the FR they fulfill. CI fails any PR that adds an env var in code without the generated table being regenerated.

**Why this priority**: Environment-variable opacity is the canonical operations-pain. P1 because (a) FR-610 + FR-616 are the canonical contracts; (b) a super admin's first 30 minutes on the platform involve setting env vars (per the FR-568 first-install checklist); (c) drift between code and docs is a security risk (e.g., a new `PLATFORM_*_PASSWORD` env var added to code but not documented means operators don't know how to set it).

**Independent Test**: Open the Configuration Reference > Environment Variables page; search for `PLATFORM_SUPERADMIN_PASSWORD_FILE`; verify (a) the entry exists; (b) description matches FR-004's exact text ("path to a file containing the password, for compatibility with Docker secrets, sealed-secrets, and CI/CD secret stores"); (c) security sensitivity is `sensitive`; (d) the variable links to `superadmin.passwordSecretRef` Helm value AND to FR-004; (e) submit a synthetic PR adding a new `os.getenv("PLATFORM_NEW_VAR_FOR_TEST")` call to a Python file; verify CI fails with "env-var-doc drift" until the generated table is regenerated and committed.

**Acceptance Scenarios**:

1. **Given** the codebase has N `os.getenv()` calls in Python + M `os.Getenv()` calls in Go + K `valueFrom: env:` references in Helm, **When** `scripts/generate-env-docs.py` runs, **Then** the output table has N+M+K rows (deduplicated by variable name) with the canonical metadata.
2. **Given** a developer adds a new env var in code without updating the docs, **When** the PR's CI runs, **Then** the docs-build job fails with a clear "env-var-doc drift detected: PLATFORM_X is in code but not in the reference table".
3. **Given** the super admin clicks the entry for `PLATFORM_SUPERADMIN_PASSWORD_FILE`, **When** the page renders, **Then** they see the security classification, the linked Helm value, the linked FR-004, and the description.

---

### User Story 4 - Spanish-Speaking User Reads the User Guide (Priority: P2)

A Spanish-speaking consumer wants to learn how to use the platform's marketplace + conversation features. They navigate to the docs site, toggle the language to "Español", browse the User Guide section. Per FR-620, user-facing sections (Getting Started, User Guide, Administrator Guide) are localized into 6 languages; technical sections (Developer Guide, Architecture, API Reference) remain English-only with clear labels indicating their English-only status. Localized screenshots are used for UI-referencing pages; architecture diagrams remain English-labelled (per FR-603 — diagrams are language-neutral). The language toggle preserves page context — switching from `/user-guide/discovering-agents/` in English to Spanish lands on `/es/user-guide/discovering-agents/`, NOT on the Spanish home page.

**Why this priority**: User-guide localization is the canonical multilingual customer-experience contract. P2 because (a) FR-620 is the canonical contract; (b) user-facing localization signals organisation-level commitment to non-English audiences; (c) the localization workflow is reused from feature 083 (UI strings) + feature 088 (READMEs).

**Independent Test**: Open `/user-guide/` in English; click the language toggle to "Español"; verify (a) the URL becomes `/es/user-guide/...` (page-context preserved); (b) the page content is in Spanish; (c) navigate to `/api-reference/`; verify the page is English-only with a clear label "This section is English-only"; (d) repeat the language toggle test in 5 other locales; (e) submit a synthetic PR adding a new H2 to the canonical English User Guide page WITHOUT updating localized variants — verify the docs CI flags the drift per FR-616.

**Acceptance Scenarios**:

1. **Given** the User Guide is open in English at `/user-guide/discovering-agents/`, **When** the user clicks the language toggle to "Español", **Then** the URL becomes `/es/user-guide/discovering-agents/` with the page content in Spanish.
2. **Given** the user navigates to a technical section (e.g., `/architecture/`), **When** the page renders, **Then** a clear banner indicates "This section is English-only" and the language toggle does NOT show non-English options for that section.
3. **Given** the User Guide is rendered in Spanish, **When** the page contains a UI screenshot, **Then** the screenshot shows the Spanish UI (per FR-620 + FR-603); architecture diagrams remain English-labelled.
4. **Given** a contributor adds a new H2 section to the canonical English User Guide page, **When** the localized variants are NOT updated, **Then** the docs CI parity-check (extending feature 088's pattern to the docs tree) flags the drift with a 7-day grace window.

---

### User Story 5 - Operator Uses Runbook Library During an Incident (Priority: P1)

An on-call operator is paged at 3am with an incident. They navigate to the Operator Guide > Runbook Library section. The runbook search (FR-617 + FR-615 search functionality) finds the right runbook by symptom keyword. The runbook has clear sections: Symptom, Diagnosis, Remediation, Verification. The operator follows the steps; the incident is resolved. The runbook is versioned per platform release.

**Why this priority**: Runbooks during incidents are the canonical hot-path operator surface. P1 because (a) FR-617 enumerates the minimum 10-runbook scope (platform upgrade, migration rollback, DR restore, multi-region failover/failback, secret rotation, capacity expansion, super-admin break-glass, incident response procedures from UPD-031, LogQL cookbook); (b) without runbooks, every incident is a custom-improvised investigation; (c) runbooks are the executable evidence of operational maturity for SOC2 / ISO27001 audits.

**Independent Test**: Simulate an incident (e.g., "Loki ingestion broken — logs not flowing"); navigate to the docs site; search "Loki ingestion"; verify the runbook is found; follow the runbook's Symptom → Diagnosis → Remediation → Verification sections; the incident is resolved. Repeat for the canonical 10 FR-617 runbooks (platform upgrade, migration rollback, DR restore, multi-region failover, multi-region failback, secret rotation, capacity expansion, super-admin break-glass, incident response, LogQL cookbook). Verify each runbook is linked from feature 080's incident-response dashboard (UPD-031 deep-link integration).

**Acceptance Scenarios**:

1. **Given** the operator is on the docs site, **When** they search "Loki ingestion outage", **Then** the runbook is the top result with its symptom keywords matched.
2. **Given** a runbook is open, **When** the operator reads it, **Then** the Symptom / Diagnosis / Remediation / Verification sections are clearly labelled and self-contained.
3. **Given** UPD-031's incident dashboard surfaces a "View runbook" link, **When** the operator clicks it, **Then** the docs site opens at the matching runbook with deep-linked anchor.
4. **Given** a new platform version is released, **When** the operator switches the docs site's version selector, **Then** the runbook library shows the version-specific content (FR-615's versioning).

---

### Edge Cases

- **FR reference drift**: a PR renames or renumbers an FR; documentation references become stale. The CI check per FR-616 detects this and blocks merge until resolved.
- **Env var added in code without doc update**: `scripts/generate-env-docs.py` reads the codebase and outputs a canonical list; CI diffs against the committed Configuration Reference and fails on mismatch per FR-610 + FR-616.
- **Helm value renamed**: `helm-docs` regenerates from YAML comments; CI fails if regenerated output differs from the committed docs per FR-611 + FR-616.
- **Documentation site build failure**: CI fails the PR with an actionable error message; the build job's last 100 lines of output are surfaced as PR comment.
- **External link rot**: weekly scheduled link checker (extension of feature 088's `docs-external-links.yml` pattern) opens an issue with broken links; non-blocking for PRs.
- **Localized screenshot drift from UI changes**: when the UI changes (e.g., a button is renamed in English), the localized screenshots become stale. The translation vendor workflow includes a "screenshot QA pass" gate; CI flags missing localized screenshot updates with the same 7-day grace window as feature 088's parity check.
- **Hetzner Terraform modules missing**: per plan correction §4, the modules are an external dependency. If they don't exist by the time T071 (Hetzner install verification) runs, the verification is BLOCKED until the modules are provided.
- **Existing `mkdocs.yml` `site_url`** points to GitHub Pages; the brownfield input proposes `docs.musematic.ai`. UPD-039 ships GitHub Pages first per spec correction §7 + adds a CNAME so `docs.musematic.ai` resolves to GitHub Pages.
- **Localized version of the Hetzner installation guide**: per FR-620, technical sections (Installation Guides) are English-only. The Hetzner guide is English-only; localized customers can request translation as a follow-up.
- **API reference rebuild on every OpenAPI change**: per FR-619, the API reference is auto-regenerated from the OpenAPI spec. The docs CI workflow includes a step that fetches the latest OpenAPI spec from `apps/control-plane/src/platform/api/openapi.json` (or runs the platform locally and curls `/api/openapi.json`) and rebuilds Redoc / Swagger UI. PRs that change the API trigger a docs rebuild automatically.
- **Documentation versioning across platform versions**: per FR-615, the docs site supports versioning. UPD-039 ships with version `1.3.0` (the current release) initially; older versions are added retroactively if archive copies exist.
- **`SECURITY.md` doesn't exist at root**: per spec correction §5 + plan correction §5, UPD-039 creates this file with the responsible-disclosure policy + PGP key + security contact email per FR-618.
- **`docs.musematic.ai` DNS record not yet present**: the docs site initially serves from `https://gntik-ai.github.io/musematic/`; the CNAME `docs.musematic.ai` → `gntik-ai.github.io` is added by an operator-driven DNS task (NOT automated by this feature).
- **Auto-generated env-var docs include test-only variables**: `scripts/generate-env-docs.py` includes a deny-list pattern (e.g., variables prefixed with `TEST_*`, `MUSEMATIC_E2E_*`) to exclude test-mode variables from the production-facing reference per the brownfield's "security classification (inferred from variable name heuristics)".
- **Stale Helm-docs output committed**: a developer modifies a Helm value's comment but forgets to regenerate the docs; CI catches this per FR-611's regeneration check.
- **Existing `docs/` files with FR references that fall outside the new section structure**: e.g., the existing `docs/agents.md` (~ 885 bytes — verified per inventory) references FR-300 series. UPD-039 moves it into `developer-guide/` per FR-605 and updates the FR-references-CI check to scan the new location.

## Requirements *(mandatory)*

### Functional Requirements (canonical citations from `docs/functional-requirements-revised-v6.md`)

**Section 112 — Comprehensive Documentation and Installation Guides** (FR-605 through FR-620):

- **FR-605**: 11 top-level documentation sections (Getting Started + User Guide + Admin Guide + Operator Guide + Developer Guide + API Reference + Architecture + Installation Guides + Configuration Reference + Security Guide + Release Notes).
- **FR-606**: kind installation guide (15 minutes target).
- **FR-607**: k3s installation guide (single-node lab).
- **FR-608**: Hetzner installation guide with full production-grade detail (Terraform + kubeadm + addons + ingress + storage + observability + platform Helm + DNS + TLS + backup + monitoring + runbooks).
- **FR-609**: Managed K8s installation guide (GKE + EKS + AKS).
- **FR-610**: Auto-generated env vars reference table.
- **FR-611**: Auto-generated Helm values reference via `helm-docs`.
- **FR-612**: Feature flag reference (every flag with name, default, scope, controlled-by-role, description, related FRs, rollout history).
- **FR-613**: URL and domain scheme documentation (canonical `app.musematic.ai` / `api.musematic.ai` / `grafana.musematic.ai` for prod; `dev.*.musematic.ai` for dev; per-environment `{env}.*.musematic.ai` pattern; CORS policy; cookie domain separation).
- **FR-614**: TLS strategy documentation (Let's Encrypt DNS-01 wildcard + cert-manager + renewal + alerting + emergency manual renewal runbook).
- **FR-615**: Site technology — static site generator (Docusaurus / MkDocs Material / equivalent) with search, versioning, language toggle, dark mode, accessibility AA.
- **FR-616**: CI checks for FR drift + env-var-doc drift + Helm-values-doc drift.
- **FR-617**: Operator runbook library (10+ runbooks per the FR enumeration).
- **FR-618**: Security guide with threat model + compliance mapping (SOC2 + ISO27001 + GDPR + HIPAA + PCI) + responsible disclosure policy (`SECURITY.md` at repo root) + PGP key + security contact.
- **FR-619**: Auto-generated API reference quality (OpenAPI 3.1 + Swagger UI + Redoc + 4-language code samples + auth guide + rate-limit docs + error code catalog + API changelog).
- **FR-620**: Documentation localization policy (User-facing in 6 languages; technical English-only).

### Key Entities

- **Documentation site at `https://gntik-ai.github.io/musematic/`** (initial GitHub Pages URL per spec correction §7) — built with MkDocs Material per existing `mkdocs.yml` config; the `docs.musematic.ai` CNAME is added as a follow-up.
- **Documentation tree** (`docs/`) — REORGANIZED into the FR-605 11-section structure via `git mv` per spec correction §3; the existing `administration/`, `development/`, etc. subdirectories are absorbed into the new structure.
- **`SECURITY.md`** at the repo root — NEW per FR-618 + spec correction §5.
- **Auto-generation tooling**:
  - `scripts/generate-env-docs.py` — NEW Python script (AST-walker over Python + Go + Helm) producing the canonical env-var reference table per FR-610.
  - `helm-docs` — NEW dev-tool dependency (NOT runtime) installed in the docs-build CI step; regenerates the Helm values reference per FR-611.
  - `scripts/check-doc-references.py` — NEW Python script scanning `docs/` for FR references and validating per FR-616.
- **Runbook library** (`docs/operator-guide/runbooks/`) — 10+ runbooks per FR-617, each with Symptom / Diagnosis / Remediation / Verification sections.
- **API Reference embedding** (`docs/api-reference/`) — Redoc + Swagger UI embedding the OpenAPI 3.1 spec (auto-fetched from the running platform per FR-619 + FR-497).
- **Localized User / Admin / Getting Started Guides** — translated into the 6 supported locales per FR-620 (English, Spanish, German, French, Italian, Simplified Chinese — NOT Japanese per spec correction §6).
- **Architecture section** (`docs/architecture/`) — REUSES the `docs/assets/architecture-overview.svg` from feature 088 / UPD-038 + the existing `software-architecture-v5.md` + `system-architecture-v5.md` files.
- **Hetzner installation guide** (`docs/installation/hetzner.md`) — flagship FR-608 guide; references Terraform modules at `terraform/environments/production/` (modules MUST exist by the time T071 verifies the guide end-to-end per spec correction §4).
- **Configuration Reference** (`docs/configuration/`) — three pages: env-vars (auto-generated by T020), Helm values (auto-generated by T030), feature flags (manual but reviewed against the FR-584 inventory).
- **CI workflow integrations** (`.github/workflows/`):
  - `ci.yml` (existing) — extended with a new `docs-staleness` job per FR-616 (env-var drift, Helm-values drift, FR-reference drift checks); the existing `dorny/paths-filter@v3` adds a `docs: ['docs/**', 'mkdocs.yml']` filter.
  - `docs-build.yml` (NEW) — builds the MkDocs site on every PR touching `docs/` AND on every push to `main` (deploys to GitHub Pages via the `peaceiris/actions-gh-pages@v3` action or equivalent).
  - `docs-external-links.yml` (extended from feature 088) — extended to scan the docs tree's external links weekly per the existing pattern.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 11 FR-605 top-level sections exist on the docs site with at least one page each; verified by an automated link-check pass over the site map.
- **SC-002**: The kind installation guide reaches a working local install in ≤ 15 minutes per FR-606 — verified by a usability test with at least 3 fresh evaluators.
- **SC-003**: The k3s installation guide reaches a working single-node install in ≤ 30 minutes per FR-607 — verified by at least one end-to-end test on a fresh Ubuntu 22.04+ VM.
- **SC-004**: The Hetzner installation guide reaches a working production install in ≤ 3 hours per FR-608 + spec User Story 1 — verified by at least one end-to-end test on a fresh Hetzner Cloud account; the verification record is captured in `specs/089-comprehensive-documentation-site/contracts/hetzner-install-verification.md`.
- **SC-005**: The managed K8s installation guide is verified on at least one of GKE / EKS / AKS per FR-609 — the chosen cloud is documented; the other two are referenced via cloud-specific notes.
- **SC-006**: The auto-generated env-var reference table at `docs/configuration/environment-variables.md` covers every `os.getenv()` call in Python + every `os.Getenv()` call in Go + every `valueFrom: env:` in Helm; CI fails any PR adding an env var without regenerating the table per FR-610.
- **SC-007**: The auto-generated Helm values reference at `docs/configuration/helm-values.md` is regenerated by `helm-docs` from YAML comments; CI fails any PR modifying `deploy/helm/**/values.yaml` without regenerating the reference per FR-611.
- **SC-008**: The feature flag reference at `docs/configuration/feature-flags.md` lists every flag from the FR-584 inventory + every additional flag that landed via UPD-036/037/038 (Phase 086+); each flag has the required columns (name, default, scope, controlled-by-role, description, related FRs, rollout history) per FR-612.
- **SC-009**: The URL and domain scheme is documented at `docs/configuration/url-scheme.md` per FR-613; the document includes the canonical production URLs (`app.musematic.ai`, `api.musematic.ai`, `grafana.musematic.ai`), the dev URLs (`dev.*.musematic.ai`), the per-environment pattern, the CORS policy, and the cookie-domain separation.
- **SC-010**: The TLS strategy is documented at `docs/configuration/tls-strategy.md` per FR-614 with the Let's Encrypt DNS-01 wildcard + cert-manager + renewal + alerting + emergency manual renewal runbook.
- **SC-011**: The docs site supports search per FR-615 — the MkDocs Material built-in search returns relevant results within 500 ms p95 for typical queries (verified by a usability test with 5 search queries).
- **SC-012**: The docs site supports versioning per FR-615 — switching the version selector loads the version-specific content; URL paths include the version segment (e.g., `/v1.3.0/user-guide/...`).
- **SC-013**: The docs site supports a language toggle per FR-615 + FR-620 — switching from English to Spanish on a localized page preserves the page context (the URL becomes `/es/user-guide/...`); technical sections (API Reference, Developer Guide, Architecture) clearly label their English-only status.
- **SC-014**: The docs site is dark-mode-capable per FR-615 — toggling dark mode preserves the user's preference across pages (uses `localStorage`).
- **SC-015**: The docs site passes axe-core AA scan with zero violations per FR-488 + the existing CI gate from feature 083.
- **SC-016**: The CI staleness checks per FR-616 run on every PR touching `docs/` OR FR files: (a) FR-reference drift via `scripts/check-doc-references.py`; (b) env-var-doc drift via `scripts/generate-env-docs.py`; (c) Helm-values-doc drift via `helm-docs --check`. All three exit non-zero on drift.
- **SC-017**: The runbook library at `docs/operator-guide/runbooks/` contains at least 10 runbooks per FR-617 — the canonical 10: platform upgrade, database migration rollback, DR restore from backup, multi-region failover, multi-region failback, secret rotation, capacity expansion, super-admin break-glass, incident response procedures (linked to UPD-031), LogQL cookbook for UPD-034 dashboards. Each runbook has Symptom / Diagnosis / Remediation / Verification sections.
- **SC-018**: The Security Guide at `docs/security/` includes a threat model + compliance mapping + responsible disclosure policy per FR-618. The repo root has `SECURITY.md` linking to the docs site's full Security Guide.
- **SC-019**: The API Reference auto-regenerates from the OpenAPI 3.1 spec per FR-619; code samples in Python / Go / TypeScript / curl are provided for every endpoint; the API changelog covers per-version backward-compatibility annotations.
- **SC-020**: User-facing sections (Getting Started, User Guide, Admin Guide) are translated into the 6 supported locales per FR-620; technical sections (Developer Guide, Architecture, API Reference) are English-only with clear labels indicating English-only status.

## Assumptions

- **MkDocs Material is the docs-site generator** per spec correction §1. The existing `mkdocs.yml` is extended; no migration to Docusaurus.
- **The Hetzner Terraform modules either exist as a separate repo OR are committed in this feature** per spec correction §4. The plan phase decides; T071 (Hetzner install verification) is BLOCKED until the modules are available.
- **The translation vendor used by features 083 (UI strings) + 088 (READMEs) is reused** for User Guide / Admin Guide / Getting Started localization.
- **GitHub Pages is the initial docs-site host** per spec correction §7; the `docs.musematic.ai` CNAME is added by an operator-driven DNS task (not part of this feature).
- **The OpenAPI 3.1 spec is generated by the running platform** per FR-497 (feature 015 / Next.js scaffold + FastAPI). UPD-039 fetches the spec via a CI step that runs the platform locally OR by checking in a snapshot of the spec.
- **`helm-docs` is acceptable as a dev-tool dependency** (installed in CI only, NOT a runtime dependency).
- **The 6-locale set per FR-620 (English, Spanish, Italian, German, French, Simplified Chinese) is the official supported set**, distinct from the 7 catalogs on disk for UI strings (which include `ja` per spec correction §6).
- **Out of scope:**
  - **Hetzner Hetzner-hosted docs site at `docs.musematic.ai`.** Initial deploy is GitHub Pages; migration is a follow-up.
  - **Algolia DocSearch.** Built-in MkDocs Material search is sufficient at the docs site's initial scale; Algolia is a follow-up.
  - **Adding new locales beyond the 6 in FR-620.** Japanese remains UI-only per spec correction §6.
  - **Mobile app for the docs site.** The MkDocs Material site is responsive; a native mobile app is out of scope.
  - **Per-version archived docs.** UPD-039 ships v1.3.0 only; older versions are added retroactively if archive copies exist.
  - **Translation of technical sections (Developer Guide, Architecture, API Reference).** Per FR-620, these are English-only.
  - **Translation of installation guides.** Installation guides are technical (Operator audience) per FR-620 and stay English-only.
  - **Auto-generated client SDKs.** The API Reference includes code samples per FR-619 but does NOT auto-generate client SDKs; SDK generation is feature 092's scope (or later).
  - **Backward-compatibility shims for old docs URLs that don't redirect.** UPD-039 uses `mkdocs-redirects` plugin per spec correction §3 to preserve the old `administration/` / `operations/` / etc. paths; non-existent old paths return 404 (acceptable for a docs site).
