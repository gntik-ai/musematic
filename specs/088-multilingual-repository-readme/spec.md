# Feature Specification: Multilingual Repository README

**Feature Branch**: `088-multilingual-repository-readme`
**Created**: 2026-04-27
**Status**: Draft
**Input**: User description: "Ship the canonical English `README.md` at the repository root plus five localized variants (`README.es.md`, `README.it.md`, `README.de.md`, `README.fr.md`, `README.zh.md`) following FR-600 / FR-601 / FR-602 / FR-603 / FR-604. Each README is a self-contained introduction with 11 sections (tagline, badges, what-is, capabilities, quick-start, installation, architecture, documentation index, contributing, license, community). A language switcher bar at the top of every variant links to the others. A new CI script `scripts/check-readme-parity.py` enforces section-heading + badge + link-count parity across all 6 variants, with a 7-day translation grace window before drift becomes a hard CI failure."

> **Constitutional anchor:** This feature IS the constitutionally-named **UPD-038** ("Multilingual README") declared in Constitution line 8 (audit-pass roster). The feature delivers FR-600 through FR-604 (Section 111 of the FR document, lines 2211-2238). Every constitutional rule that bears on this feature is in those FRs — there is no separate constitution rule for documentation translations beyond the 7-day grace window codified in FR-602.

> **Scope discipline:** This feature builds on, but does NOT re-implement, the artifacts owned by:
> - **The existing repository structure** — the on-disk `docs/` tree (subdirectories `development/`, `operations/`, `features/`, `integrations/`, `administration/`) is the documentation surface UPD-038's READMEs link to. UPD-038 does NOT reorganize the docs tree; the docs reorganization is feature 089 / UPD-039's responsibility per FR-605 (separate feature).
> - **The existing `Makefile`** — the `make dev-up` quick-start command is verified to exist at `Makefile:38`. UPD-038's READMEs reference it AS-IS; no Makefile changes.
> - **Existing CI workflows at `.github/workflows/`** (5 workflows: `build-cli.yml`, `ci.yml`, `deploy.yml`, `e2e.yml`, `sdks.yml`) — UPD-038 adds the README parity check as a new step inside the existing `ci.yml` workflow, NOT a new workflow file.
> - **Feature 083 (Accessibility & i18n) translation-vendor workflow** — UPD-038 reuses the same translation vendor + the same 7-day SLA pattern feature 083 established for UI strings; the README translations follow the same workflow but produce a different artifact (Markdown files instead of JSON catalogs).

> **Brownfield-input reconciliations** (full detail captured in planning-input.md and re-verified during the plan phase):
> 1. **6 README variants total, not "5 localized" alone.** The brownfield input writes "five localized variants (Spanish, Italian, German, French, Simplified Chinese)" and FR-600 enumerates 6 file names total: `README.md` (English canonical) + `README.es.md` + `README.it.md` + `README.de.md` + `README.fr.md` + `README.zh.md`. The spec adopts the **6-files-total interpretation**: the canonical English `README.md` PLUS 5 localized variants. The brownfield's "five" wording refers to the localized count; the canonical English is the 6th and the GitHub default.
> 2. **Missing root files referenced by READMEs.** The on-disk inventory confirms NO `README.md`, NO `LICENSE`, NO `CONTRIBUTING.md`, NO `SECURITY.md` exist at the repo root today. The brownfield README template references `./CONTRIBUTING.md`, `./LICENSE`, and `./SECURITY.md` — these links would 404 if the files are missing. **Resolution:** UPD-038's scope is the 6 README files + the parity-check script; the LICENSE / CONTRIBUTING / SECURITY files are OUT OF SCOPE (separate features or admin tasks). UPD-038's READMEs reference these files as future-state links; the parity-check script's link-validation pass treats local file links as informational warnings (NOT failures) until the referenced files exist.
> 3. **Documentation index links.** The brownfield README template references `./docs/user-guide/`, `./docs/admin-guide/`, `./docs/operator-guide/`, `./docs/developer-guide/`, `./docs/api/`, `./docs/architecture/`. The on-disk `docs/` tree has different subdirectories (`development/`, `operations/`, `features/`, `integrations/`, `administration/`). **Resolution:** UPD-038 uses links matching the on-disk tree TODAY; feature 089 / UPD-039 reorganizes the docs tree per FR-605, at which point UPD-038's READMEs are updated as part of that feature's scope. The plan phase verifies the on-disk tree at the moment of authoring and links accordingly.
> 4. **Architecture diagram path.** The brownfield template references `./docs/assets/architecture-overview.svg`. The on-disk inventory confirms this file does NOT exist (no `docs/assets/` directory). **Resolution:** UPD-038 either (a) creates a placeholder SVG in this feature OR (b) references an existing diagram path that is on disk OR (c) falls back to an inline ASCII art / text description if no diagram exists. The plan phase chooses based on what is actually on disk; the spec captures the requirement that the diagram MUST be reachable + render correctly per FR-603 + FR-604.
> 5. **`make dev-up` quick-start command verified.** The on-disk `Makefile:38` has the `dev-up` target. UPD-038's quick-start section uses this verbatim.
> 6. **GitHub repo URL.** The brownfield references `gntik-ai/musematic` — verified consistent with the recent PR merge commits in the repo (`Merge pull request #86 from gntik-ai/...`). The badges' shields.io URLs use this org/repo path.
> 7. **Language switcher byte-equivalence.** The brownfield says the language switcher is identical across all 6 variants. **Clarification:** the bar's MARKDOWN is byte-identical (every link in every variant points to the same 6 files); only the surrounding prose is translated. The parity-check script verifies this by comparing the language-switcher block character-for-character.
> 8. **Translation vendor SLA.** The brownfield specifies a 7-day grace window. FR-602 explicitly codifies this. The plan phase wires the CI script's hard-fail-after-7-days behaviour to a tracked GitHub issue per the brownfield's "Grace period is trackable via a GitHub issue auto-created by the CI check" acceptance criterion.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - First-Time Visitor Lands on the GitHub Repo (Priority: P1)

A developer hears about Musematic and lands on the GitHub repo. Within 60 seconds of viewing the page they MUST be able to: (a) understand what Musematic is and for whom; (b) see a quick-start command without scrolling deep; (c) see badges showing build status, license, supported Kubernetes versions, current version; (d) see a single architecture diagram summarising the system; (e) find links to detailed guides without hunting. If the README does not exist (the current state — no `README.md` at the root) OR is a stub, the developer bounces.

**Why this priority**: A first-time visitor's bounce-or-stay decision is the single most important onboarding-funnel event. P1 because (a) without a discoverable README, the project's GitHub presence is invisible — visitors land on a tree of source files with zero context; (b) every other onboarding flow (signup, OAuth, install) is unreachable until visitors decide to explore the repo; (c) FR-600 + FR-601 are the canonical "what to put in the README" contracts.

**Independent Test**: Create a fresh GitHub user account; navigate to the repo's GitHub page; read the README top-to-bottom in 2 minutes (the rendered Markdown view, NOT the raw file). Verify: (a) the top section states what Musematic is + for whom; (b) the quick-start `git clone … && make dev-up` command is in the first viewport (~ 600 px); (c) at least 4 badges render correctly via shields.io; (d) the architecture diagram renders inline (or, per plan correction §4, an inline text description provides equivalent context); (e) at least 6 links to detailed guides are visible without scrolling beyond the architecture section. Repeat for each of the 5 localized variants.

**Acceptance Scenarios**:

1. **Given** the repo's GitHub page renders the canonical English `README.md`, **When** a first-time visitor scrolls top-to-bottom, **Then** all 11 sections from FR-601 are present in the documented order: tagline + 1-paragraph description, badges, "What is Musematic?", core capabilities, quick start, installation options, architecture at a glance, documentation index, contributing, license, community and support.
2. **Given** a Spanish-speaking visitor opens `README.es.md` (e.g., via direct GitHub URL or via the language switcher bar), **When** they scroll top-to-bottom, **Then** all 11 sections are present, the prose is translated to Spanish (per a native-speaker review), and code blocks (commands, file paths) remain in English per spec edge-case below.
3. **Given** any of the 6 README variants renders, **When** the visitor checks the language-switcher bar at the top, **Then** the bar links to ALL 6 variants (English + 5 localized) including a link back to itself for clarity (which renders as a non-link "Current language" indicator OR a link that no-ops — implementation choice).
4. **Given** the repo is cloned, **When** a developer runs the quick-start `make dev-up` command per FR-601 §5, **Then** a kind cluster spins up, Helm charts install, seed data loads, and `http://localhost:8080` becomes reachable per the existing `Makefile:38` target — this is verified by the existing feature 071 E2E harness, NOT by this feature.
5. **Given** the badges are configured, **When** the README renders, **Then** each badge fetches its current state from shields.io (build status from `.github/workflows/ci.yml`, license from `LICENSE` if present, Kubernetes 1.28+ static badge, version from the latest GitHub release). If `LICENSE` is missing per plan correction §2, the license badge renders as "License not available" or similar — a graceful degrade, NOT a broken image.

---

### User Story 2 - Spanish-Speaking Evaluator Reviews in Native Language (Priority: P1)

A Spanish-speaking product manager wants to evaluate Musematic in their native language before involving engineering. They click the "Español" link at the top of the English README (or land directly on `README.es.md` via search). They read the Spanish README top-to-bottom and form a sufficient understanding to recommend the platform to engineering — without needing English support. The translation MUST be idiomatic per a native reviewer's check; commands and code blocks remain in English (commands are universal — `git clone`, `make dev-up`).

**Why this priority**: Multilingual repository presence is the canonical signal that a project takes non-English audiences seriously. P1 because (a) FR-600 + FR-602 explicitly mandate the multilingual surface as production artifacts; (b) Musematic targets enterprise customers whose evaluation teams may be non-English-speaking; (c) the same workflow extends to UI strings via feature 083 — both are part of the platform's i18n discipline.

**Independent Test**: A Spanish-native reviewer reads `README.es.md` top-to-bottom; rates the translation quality on a 1-5 scale (target: ≥ 4); verifies all 11 sections are present; verifies the language-switcher bar at the top links back to English + the other 4 localized variants; verifies all internal links work (no dead links to localized docs that haven't been translated yet — those links point to English equivalents per plan correction §3 fallback). Repeat for Italian, German, French, Simplified Chinese with their respective native reviewers.

**Acceptance Scenarios**:

1. **Given** `README.es.md` is the entry point, **When** a Spanish-native reviewer reads top-to-bottom, **Then** the prose is idiomatic (≥ 4/5 quality rating), all 11 FR-601 sections are present, and the language-switcher bar at the top links to all 6 variants.
2. **Given** any localized variant, **When** the reviewer checks code blocks and command examples, **Then** they remain in English per the spec edge-case below (commands are universal; translating them would break copy-paste workflows).
3. **Given** any localized variant, **When** the reviewer follows internal documentation links, **Then** the links work (point to existing files in `docs/` per plan correction §3 — currently English-only; the plan phase verifies what exists on disk).
4. **Given** the architecture diagram is referenced, **When** the localized variant renders, **Then** the SAME diagram is reused per FR-603 (architecture diagrams are language-neutral; only UI screenshots require per-language variants).
5. **Given** the 5 localized variants exist, **When** the parity-check script runs, **Then** every section heading + every badge + every link from the canonical English README is present (in translated form for headings, identical for badges + link counts) per FR-602.

---

### User Story 3 - Translation Drift Detection on PR (Priority: P2)

A contributor adds a new section to the canonical English `README.md` without updating the 5 localized variants. They submit a PR. The CI pipeline's parity-check step detects the drift and posts a friendly warning comment on the PR linking to the diff (NOT a hard fail within the 7-day grace window per FR-602). After 7 days, if the localized variants are still missing the section, the parity-check fails the build for any subsequent PR touching the README until parity is restored. The 7-day grace window is tracked as an auto-created GitHub issue.

**Why this priority**: Without the parity check, translation drift is invisible until a non-English visitor encounters the broken section — by then the damage to trust is done. P2 because (a) the parity check is a quality gate, not a feature; (b) the 7-day grace window allows reasonable translation-vendor turnaround; (c) the gate fails closed (hard fail after 7 days) so drift cannot accumulate.

**Independent Test**: Submit a test PR adding a new H2 section to `README.md` only (not to the 5 localized variants); verify (a) the parity-check CI step posts a comment on the PR with the diff (the missing section heading per locale); (b) the comment is non-blocking — the PR can still merge with maintainer approval; (c) a GitHub issue is auto-created tracking the 7-day grace window with the PR number + the missing heading; (d) after 7 days (simulated by adjusting the grace window to 1 minute for the test), a subsequent PR touching `README.md` fails the parity check unless the `docs-translation-exempt` label is applied; (e) the script's exit codes are conventional (0 = pass, 1 = drift detected, 2 = hard fail).

**Acceptance Scenarios**:

1. **Given** a PR adds a new section heading to `README.md` and not to the 5 localized variants, **When** `scripts/check-readme-parity.py` runs in CI, **Then** the script exits with code 1 (warning) AND posts a GitHub-comment-friendly diff to the PR identifying the missing headings per locale.
2. **Given** the warning is posted, **When** the maintainer or contributor merges the PR, **Then** an auto-created GitHub issue tracks the 7-day grace window — the issue title includes the PR number and the missing heading; the issue body includes the diff and a deadline timestamp.
3. **Given** 7 days elapse without the localized variants catching up, **When** any subsequent PR touching `README.md` runs CI, **Then** the parity check exits with code 2 (hard fail) AND blocks the PR merge until parity is restored — UNLESS the maintainer applies the `docs-translation-exempt` label, which downgrades the gate to a warning.
4. **Given** the `docs-translation-exempt` label is applied (e.g., for a security-disclosure PR requiring immediate English-only publication), **When** the CI runs, **Then** a follow-up GitHub issue is auto-created with a 30-day hard SLA to backfill translations per the brownfield's "Translation Management" section.
5. **Given** an existing PR touches a single localized variant only (e.g., a typo fix in `README.es.md`), **When** the parity check runs, **Then** the script does NOT flag drift (typo fixes are translation corrections that don't require updates to other variants) per the spec edge-case below.
6. **Given** the parity-check script runs, **When** it validates internal links, **Then** broken links to local files are reported as warnings (NOT failures) per plan correction §2 — the LICENSE / CONTRIBUTING / SECURITY files may not yet exist; the warnings are tracked separately.

---

### Edge Cases

- **No README at root today**: the on-disk inventory confirms there is no `README.md` at the repo root; UPD-038 creates all 6 README variants from scratch in this feature.
- **New section added in English only**: parity check warns within the 7-day grace window; hard fail after 7 days unless `docs-translation-exempt` label applied.
- **Translation typo fix**: a PR touching only one localized variant (e.g., fixing a typo in `README.es.md`) does NOT require updates to other variants — typo fixes are corrections, not new content per the spec edge-case.
- **Code blocks in localized variants**: code blocks (commands, file paths) remain in English; commands like `git clone`, `make dev-up`, file paths like `./docs/...` are NOT translated. This is a hard rule — translating commands would break copy-paste workflows.
- **External link rot**: external link validation (e.g., shields.io badge URLs, GitHub Discussions links) is NOT run on every PR per plan correction §10 — it runs WEEKLY via a separate scheduled workflow to avoid flaky CI failures from transient external outages.
- **GitHub-specific links in localized variants**: links to GitHub Issues, Discussions, Releases stay valid even if the repo is mirrored to GitLab per FR-604 (the mirror would map them, NOT break them).
- **Localized UI screenshots**: per FR-603, screenshots of the UI in the target language MAY be included per-variant but are NOT required; the architecture diagrams MUST stay in English (language-neutral) and shared across all 6 variants.
- **Emergency security disclosure**: a maintainer applies the `docs-translation-exempt` label; the disclosure ships in English only; a follow-up GitHub issue tracks the 30-day backfill SLA per the brownfield's "Translation Management" section.
- **Language switcher byte-equivalence**: the language-switcher bar at the top of every variant is byte-identical Markdown — every link points to the same 6 files; only the surrounding prose is translated. The parity-check script verifies this by comparing the bar character-for-character.
- **Native-speaker review failures**: if a native-speaker reviewer rates a translation < 4/5, the variant is sent back to the translation vendor for revision. The CI parity check does NOT enforce translation quality (only structural parity); quality is a human gate.
- **Mirror to GitLab**: FR-604 requires the READMEs to render correctly on GitLab. The parity-check script's Markdown validation uses pandoc (a common-renderer subset) to verify cross-renderer compatibility per plan correction (deferred to plan phase).

## Requirements *(mandatory)*

### Functional Requirements (canonical citations from `docs/functional-requirements-revised-v6.md`)

**Section 111 — Multilingual README** (FR-600 through FR-604):

- **FR-600**: 6 README files at the repo root: `README.md` (English canonical, the GitHub default) + `README.es.md` + `README.it.md` + `README.de.md` + `README.fr.md` + `README.zh.md`. Each is a full self-contained introduction (NOT a stub). The English README has a top-section "Read in other languages" bar linking to each localized variant; each localized README links back to English.
- **FR-601**: Each README contains 11 sections in the canonical order: (1) project tagline + 1-paragraph description, (2) badges (build status, license, Kubernetes versions, current version), (3) "What is Musematic?", (4) core capabilities (bullet list), (5) quick start (5-minute path to running install), (6) installation options overview (kind / k3s / Hetzner / managed K8s), (7) architecture at a glance (diagram + 3-4 paragraphs), (8) documentation index, (9) contributing, (10) license, (11) community and support.
- **FR-602**: README translations are production artifacts. Changes to canonical English README require corresponding updates to all 6 variants within the same PR OR a documented 7-day grace period during which the discrepancy is tracked as a GitHub issue. CI script `scripts/check-readme-parity.py` flags drift by comparing section headings and link integrity.
- **FR-603**: Embedded diagrams + screenshots + code blocks: architecture diagrams labelled in English are language-neutral and reusable across all 6 variants; UI screenshots MAY be localized per-variant but are NOT required. Choice favours reusability.
- **FR-604**: Each README variant renders correctly on GitHub (Markdown + GFM extensions), GitLab (compatible subset), and common Markdown renderers (pandoc, MkDocs). Links to GitHub-specific pages remain valid when mirrored to GitLab.

### Key Entities

- **Canonical English `README.md`** (NEW at repo root) — the source of truth; ~150-300 lines including badges + tagline + 11 FR-601 sections; the language-switcher bar at the top links to all 6 variants.
- **5 localized README variants** (NEW at repo root): `README.es.md`, `README.it.md`, `README.de.md`, `README.fr.md`, `README.zh.md` — each maintains FR-601 section parity with the canonical English; prose translated by the translation vendor; commands + file paths remain in English.
- **Architecture diagram** (path TBD per plan correction §4) — language-neutral; reused across all 6 variants. Either an existing on-disk SVG OR a new placeholder created in this feature OR an inline ASCII description as a fallback.
- **Parity-check script** `scripts/check-readme-parity.py` (NEW) — compares H1/H2/H3 headings + badge count + link count + language-switcher-bar byte-equivalence across all 6 variants; emits diffs on drift; exit codes: 0 (pass), 1 (drift within grace window), 2 (hard fail beyond grace window).
- **CI workflow integration** — modifies `.github/workflows/ci.yml` to add the `readme-parity` step after the existing `lint` jobs; the step runs on every PR touching `README*.md`. A separate scheduled workflow runs the EXTERNAL link validation weekly per spec edge-case.
- **GitHub issue auto-creator** — when the parity check detects drift, the CI step creates (or updates) a GitHub issue titled "README translation drift" with the PR reference + the missing headings per locale + the 7-day grace deadline.
- **`docs-translation-exempt` GitHub label** — a maintainer-applied label that downgrades the parity-check hard fail to a warning; auto-creates a 30-day-SLA follow-up issue.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 6 README files exist at the repo root with FR-601's 11 sections present in the canonical order; verified by the parity-check script's structural pass.
- **SC-002**: A first-time visitor reading the canonical English README in 2 minutes can answer (a) "what is Musematic?", (b) "for whom?", (c) "what is the quick-start command?", (d) "where do I find detailed docs?" — verified by a usability test with at least 5 fresh evaluators per the SC-002 metric.
- **SC-003**: Each of the 5 localized variants achieves a native-speaker quality rating ≥ 4/5; ratings recorded in `specs/088-multilingual-repository-readme/contracts/translation-quality-reviews.md` per locale.
- **SC-004**: All 4+ badges (build status, license, Kubernetes 1.28+, version) render correctly on GitHub; broken-image badges fail the SC; per plan correction §2 the license badge MAY render as "License not available" if the LICENSE file is missing — that's a graceful degrade, NOT an SC failure.
- **SC-005**: The language-switcher bar at the top of every README variant is byte-identical Markdown across all 6 files (every link points to the same 6 files); verified by the parity-check script's character-by-character comparison.
- **SC-006**: All internal documentation links in every variant resolve to existing files in the on-disk `docs/` tree per plan correction §3; broken links are reported as parity-check warnings, NOT failures (until the LICENSE / CONTRIBUTING / SECURITY files are added in subsequent features).
- **SC-007**: The parity-check script exits with code 0 on a fresh checkout of the canonical 6 READMEs; exit code 1 on any single-locale drift introduced by a test PR; exit code 2 after the simulated 7-day grace window.
- **SC-008**: The parity-check script's CI step posts a comment on every PR that introduces drift; the comment includes a per-locale diff of the missing headings + a link to the auto-created GitHub issue.
- **SC-009**: The auto-created GitHub issue for translation drift is titled `README translation drift: PR #{N}` and contains (a) the PR reference, (b) the missing headings per locale, (c) the 7-day grace deadline timestamp, (d) a link to the offending PR.
- **SC-010**: After 7 days, any new PR touching `README*.md` fails the CI parity check unless the `docs-translation-exempt` label is applied; the failure message includes a link to the original drift-tracking issue.
- **SC-011**: The architecture diagram referenced in every variant (path TBD per plan correction §4) is reachable AND renders inline correctly on GitHub's rendered Markdown view; SVG accessibility text is set per FR-603.
- **SC-012**: Each README variant renders correctly under pandoc (the cross-renderer fallback per FR-604) — verified by the parity-check script invoking `pandoc -f gfm -t html` on each file and asserting zero parser errors.
- **SC-013**: The CI parity-check step adds < 30 seconds to every PR's CI duration; the weekly external-link-validation workflow runs in < 5 minutes.
- **SC-014**: The translation vendor's 7-day SLA is met for ≥ 95% of README PRs (measured over the first 6 months post-feature-landing); SLA misses trigger the 30-day-backfill follow-up issue per the spec edge-case for emergency exemptions.
- **SC-015**: When the repo is mirrored to GitLab, every README variant renders correctly with all GitHub-specific links (Issues, Discussions, Releases) still valid per FR-604.

## Assumptions

- **The repo's GitHub URL is `gntik-ai/musematic`** (verified via PR merge commits in the recent git history).
- **The translation vendor used by feature 083 (Accessibility & i18n) for UI strings is reused for README translations.** Same workflow, same 7-day SLA, same quality-review process. UPD-038 does NOT introduce a new translation vendor.
- **Native-speaker reviewers are available for each locale.** The reviewers may be employees, contractors, or community contributors; the reviewer-recruitment process is OUT OF SCOPE for UPD-038 — it's a precondition.
- **The architecture diagram is created elsewhere or by this feature.** The plan phase decides between (a) creating a placeholder SVG, (b) referencing an existing diagram, or (c) using an inline text description per plan correction §4.
- **GitHub Actions are the CI substrate.** The parity-check script integrates into `.github/workflows/ci.yml` (existing). The weekly external-link-validation workflow is a NEW scheduled workflow (or a step inside an existing scheduled workflow).
- **Out of scope:**
  - **Reorganizing the docs tree.** Feature 089 / UPD-039 owns the FR-605 docs-site structure; UPD-038 links to whatever is on disk today.
  - **Creating LICENSE / CONTRIBUTING.md / SECURITY.md files.** These are referenced by the READMEs but their existence is a separate gap (likely admin tasks or follow-up features).
  - **Translating the platform UI.** Feature 083 / UPD-030 owns the UI string catalog.
  - **Translating user-facing platform documentation.** Documentation translations (the `docs/` tree) are a separate scope; UPD-038 covers ONLY the 6 README files at the repo root.
  - **Adding new locales beyond the 6 specified.** FR-600 enumerates 6; additional locales are follow-up features.
  - **Localizing UI screenshots in the README.** Per FR-603, UI screenshots MAY be localized per-variant but are NOT required; the canonical READMEs use the same English screenshots if any.
  - **Per-locale architecture diagrams.** Per FR-603, architecture diagrams stay language-neutral.
  - **Verifying translation quality via the CI script.** Quality is a human gate (native-speaker review per SC-003); the CI script enforces structural parity only.
