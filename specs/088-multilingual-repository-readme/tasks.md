# Tasks: UPD-038 — Multilingual Repository README

**Feature**: 088-multilingual-repository-readme
**Branch**: `088-multilingual-repository-readme`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

User stories (from spec.md):
- **US1 (P1)** — First-time visitor lands on the GitHub repo and decides in 60 seconds whether to keep reading (the canonical English README experience; the MVP)
- **US2 (P1)** — Spanish-speaking evaluator reviews in native language with native-speaker quality ≥ 4/5 across the 5 localized variants
- **US3 (P2)** — Translation drift detection on PR via `scripts/check-readme-parity.py` with 7-day grace window + auto-created tracking issue + `docs-translation-exempt` label override

Independent-test discipline: every US MUST be verifiable in isolation. US1 verification is a 2-minute read of the canonical English README on GitHub's rendered Markdown view. US2 is a native-speaker review per locale with the rating recorded in `contracts/translation-quality-reviews.md`. US3 is a synthetic test PR introducing single-locale drift + a 1-minute simulated grace window — verified by the script's exit codes.

**Wave-13 sub-division** (per plan.md §"Wave layout"):
- W13.0 — Setup: T001-T003
- W13A — Canonical English + diagram (Track A): T004-T010
- W13B — Parity-check script + CI (Track B): T011-T024
- W13C — Translations (Track C): T025-T032
- W13D — Finalization + polish: T033-T045

---

## Phase 1: Setup

- [X] T001 [W13.0] Verify the on-disk repo state matches the spec's correction §2-§4 + plan.md correction §2: confirm there is no `README.md` at the repo root, no `LICENSE`, no `CONTRIBUTING.md`, no `SECURITY.md`, no `docs/assets/` directory, no `docs/getting-started.md`, no `docs/install/` subdirectory; confirm the on-disk `docs/` tree has subdirectories `administration/`, `development/`, `features/`, `integrations/`, `operations/` PLUS the four top-level `.md` files (`agents.md`, `functional-requirements-revised-v6.md`, `software-architecture-v5.md`, `system-architecture-v5.md`). Document the inventory in `specs/088-multilingual-repository-readme/contracts/repo-inventory.md` (NEW file). The inventory is the input T009 consumes when authoring the Documentation Index section's links.
- [X] T002 [P] [W13.0] Verify the existing CI substrate per plan.md correction §1 + §7: read `.github/workflows/ci.yml` and confirm (a) the `dorny/paths-filter@v3` action is present at the top of the file (verified per inventory at lines 25-43); (b) the existing filter list to which UPD-038 will append the `readme: ['README*.md']` filter; (c) the workflow's `permissions:` block — UPD-038 needs `issues: write` AND `pull-requests: write` added per plan.md research R7. Document the integration plan in `specs/088-multilingual-repository-readme/contracts/ci-integration.md` (NEW file).
- [ ] T003 [P] [W13.0] Verify the translation-vendor relationship per plan.md cross-feature coordination: confirm with feature 083 / UPD-030's owner that the same vendor + 7-day SLA workflow is reusable for README translations (the brownfield input + spec assumption). Document the vendor-engagement contact + the SLA terms in `specs/088-multilingual-repository-readme/contracts/translation-vendor.md` (NEW file). If the vendor relationship is NOT yet established, T025-T029 (translations) are blocked until engagement; T004-T024 (canonical English + tooling) can proceed independently.

---

## Phase 2: Track A — Canonical English README + Architecture Diagram

**Story goal**: Author the canonical English `README.md` per FR-601's 11-section structure + create the architecture diagram + the new `docs/assets/` directory. Without this, US1 (first-time visitor) is blocked.

### Architecture diagram

- [X] T004 [W13A] Create the new `docs/assets/` directory at the repo root per plan.md correction §4 (the directory does NOT exist on disk per T001 inventory). Add a `.gitkeep` file initially OR commit the SVG from T005 alongside the directory creation. The directory is the canonical home for the architecture diagram + any future English-labelled diagrams; UI screenshots (which MAY be localized per FR-603) live in per-locale subdirectories if needed.
- [X] T005 [W13A] Author `docs/assets/architecture-overview.svg` per plan.md research R2: a single high-level diagram (~ 30-50 SVG primitives) showing the canonical platform topology — Python control plane (centre), Go satellite services (left: runtime-controller, sandbox-manager, reasoning-engine, simulation-controller), data stores (right: PostgreSQL, Redis, Qdrant, Neo4j, ClickHouse, OpenSearch, S3), Kafka event bus (top), observability stack (bottom: Prometheus, Grafana, Jaeger, Loki), Next.js frontend (far left). All labels in English per FR-603 (language-neutral asset reused across all 6 variants). The SVG MUST use inline primitives (no external font references, no external image references) so it renders consistently on GitHub, GitLab, pandoc, and MkDocs per FR-604 + plan.md research R2. Add an SVG `<title>` and `<desc>` element for accessibility per FR-488 / SC-011.

### Canonical English `README.md`

- [ ] T006 [W13A] [US1] Draft the project tagline + 1-paragraph description (FR-601 §1) in consultation with the product team for brand alignment per the brownfield input's "draft the tagline" step. The tagline is the H1 subtitle (e.g., "Musematic — Agentic Mesh Platform"); the 1-paragraph description sits below the badges and above the H2 "What is Musematic?" section. Capture the approved text in `specs/088-multilingual-repository-readme/contracts/canonical-english-content.md` (NEW file) so the translation vendor (T025-T029) has a single source of truth for the canonical English text.
- [X] T007 [W13A] [US1] Configure the 4 shields.io badges per FR-601 §2 + plan.md research R9: build status (`https://img.shields.io/github/actions/workflow/status/gntik-ai/musematic/ci.yml`), license (`https://img.shields.io/github/license/gntik-ai/musematic`), Kubernetes version (`https://img.shields.io/badge/kubernetes-1.28%2B-blue`), version (`https://img.shields.io/github/v/release/gntik-ai/musematic`). The license badge gracefully degrades to "License: not specified" when LICENSE is missing per plan.md risk-register row 11; the version badge similarly degrades when no GitHub release exists yet.
- [X] T008 [W13A] [US1] Author the language-switcher bar per FR-600 + plan.md research R6: `> **Read this in other languages**: [English](./README.md) · [Español](./README.es.md) · [Italiano](./README.it.md) · [Deutsch](./README.de.md) · [Français](./README.fr.md) · [简体中文](./README.zh.md)`. The bar is byte-identical across all 6 variants per spec edge-case "Language switcher byte-equivalence" + plan.md research R6 (locale order matches brownfield: English → Spanish → Italian → German → French → Simplified Chinese). The current-locale link is a no-op self-link per plan.md open question Q1.
- [X] T009 [US1] [W13A] Author `README.md` at the repo root per FR-601's 11 canonical sections in this exact order (matching plan.md design Track A):
  1. **Tagline + 1-paragraph description** (from T006)
  2. **Badges** (from T007)
  3. **Language-switcher bar** (from T008)
  4. **What is Musematic?** — accessible description of platform purpose, target users, differentiators (~ 200-300 words)
  5. **Core capabilities** — bullet list per the brownfield template (Agent Lifecycle Management, Multi-Agent Orchestration, Trust and Compliance, Reasoning, Evaluation, Observability, Cost Governance, Portability)
  6. **Quick start** — 5-minute path with the verified `make dev-up` command (Makefile:38) per plan.md correction §10's clarifying note about first-run-cold-cache vs steady-state
  7. **Installation options** — table of kind / k3s / Hetzner / managed K8s per FR-601 §6 with on-disk-valid links per plan.md correction §3 (e.g., point to `./deploy/helm/observability/README.md` from feature 085 if it exists, else `./docs/operations/`)
  8. **Architecture at a glance** — 3-4 paragraph description + the SVG from T005 via `![Architecture diagram](./docs/assets/architecture-overview.svg)`
  9. **Documentation index** — links matching the on-disk `docs/` tree per plan.md correction §2 + R1: `[Administration Guide](./docs/administration/)`, `[Operations Guide](./docs/operations/)`, `[Development Guide](./docs/development/)`, `[Features Documentation](./docs/features/)`, `[Integrations](./docs/integrations/)`, `[System Architecture](./docs/system-architecture-v5.md)`, `[Software Architecture](./docs/software-architecture-v5.md)`, `[Functional Requirements](./docs/functional-requirements-revised-v6.md)`
  10. **Contributing** — link to `./CONTRIBUTING.md` per FR-601 §9 (informational link per plan.md correction §2 — the file may not yet exist; the parity-check warns but does not fail)
  11. **License** — link to `./LICENSE` per FR-601 §10 (same informational-link pattern)
  Plus a final **Community and support** section per FR-601 §11 with GitHub Issues + Discussions + SECURITY.md links.
  The file totals ~150-300 lines per plan.md design Track A.
- [ ] T010 [W13A] [US1] Verify the canonical English README renders correctly on GitHub (the canonical Markdown renderer per FR-604): push a draft branch with `README.md` + `docs/assets/architecture-overview.svg`; navigate to the branch's GitHub page; verify (a) all 4 badges render correctly via shields.io; (b) the language-switcher bar renders inline as a single line on desktop viewport; (c) the architecture diagram renders inline (NOT as a broken image); (d) all on-disk links per T009 §9 resolve to existing files (broken-link-warnings are acceptable for `./CONTRIBUTING.md` + `./LICENSE` + `./SECURITY.md` per plan.md correction §2). Capture a screenshot at desktop viewport for the SC-002 usability verification (T033).

---

## Phase 3: Track B — Parity-Check Script

**Story goal**: Author `scripts/check-readme-parity.py` per plan.md design Track B canonical signature + tests + Markdown / pandoc / `gh` integration. Without this, US3 (drift detection) is unenforceable.

### Script + helpers

- [X] T011 [W13B] Create `scripts/check-readme-parity.py` per plan.md design Track B canonical signature: Python stdlib only (`re`, `pathlib`, `subprocess`, `argparse`, `json`, `os`, `sys`, `datetime`); module-level `LOCALES = ["", ".es", ".it", ".de", ".fr", ".zh"]` with canonical English first; `GRACE_WINDOW = timedelta(days=7)`; `LANGUAGE_BAR_RE` regex matching the FR-600 bar pattern. Implement helper functions per plan.md research R3: `extract_headings(content, max_level=3) -> list[tuple[int, str]]`, `count_badges(content) -> int`, `count_links(content) -> int`, `extract_language_bar(content) -> str | None`, `validate_pandoc(file: Path) -> bool` (subprocess invocation of `pandoc -f gfm -t html`), `check_grace_window(issue_number: int) -> bool` (subprocess `gh issue view --json createdAt`), `has_exempt_label(pr_number: int) -> bool` (subprocess `gh pr view --json labels`).
- [X] T012 [W13B] Implement the `main()` function per plan.md design Track B sketch: argparse with `--pr-number`, `--repo-root`, `--drift-issue` flags; reads all 6 README files; extracts canonical-English baseline (heading list, badge count, link count, language-switcher-bar); compares each of the 5 localized variants against the baseline; collects `drift` list. Exit codes per spec User Story 3 acceptance scenario 4 + SC-007: 0 (parity), 1 (drift within grace window — warning), 2 (hard fail beyond grace window OR pandoc rendering failure OR missing required file). Emits human-readable diff to stdout for the CI step's PR-comment generator.
- [X] T013 [W13B] Add the `gh` CLI authentication pattern per plan.md research R7: the script reads `GITHUB_TOKEN` from `os.environ` and passes it as `GH_TOKEN` env var to subprocess invocations of `gh issue view` and `gh pr view`. The CI workflow's `permissions:` block adds `issues: write` (for issue creation) AND `pull-requests: write` (for PR comments). The script gracefully handles missing `GITHUB_TOKEN` (e.g., when run locally outside CI) by falling back to "no tracking issue / no exempt label" — equivalent to fresh-drift behaviour.
- [X] T014 [W13B] Add the language-switcher-bar byte-equivalence check per plan.md research design + spec edge-case: `extract_language_bar()` returns the bar's exact Markdown line; the main function compares the canonical bar to each variant's bar via `==` (string equality). Mismatches emit `"{file}: language-switcher-bar byte-mismatch"` to the drift list. This is the canonical FR-600 + spec User Story 1 acceptance scenario 3 contract.

### Tests

- [X] T015 [W13B] Create `scripts/tests/__init__.py` (empty file) AND `scripts/tests/test_readme_parity.py` per plan.md technical context: pytest-based unit tests with ~ 6-8 fixtures + ~ 15 test cases covering: (a) `extract_headings()` extracts H1/H2/H3 correctly + ignores H4+; (b) `count_badges()` distinguishes badges (`![x](y)`) from links (`[x](y)`); (c) `count_links()` excludes badges; (d) `extract_language_bar()` returns None when missing, returns the bar otherwise; (e) `validate_pandoc()` returns False on malformed Markdown; (f) parity-detection: identical 6 files exit 0; (g) drift-detection: missing heading in one variant exits 1; (h) drift + exempt label: exits 1 (downgraded, with warning); (i) drift + grace expired + no exempt label: exits 2; (j) language-switcher-bar mismatch: exits 1; (k) pandoc rendering failure: exits 2 immediately (no grace window applies); (l) missing locale file: exits 2; (m) helper-function unit tests for each regex; (n) integration test using a temp directory with 6 fake READMEs.
- [X] T016 [W13B] Run `pytest scripts/tests/test_readme_parity.py -v` locally; assert all tests pass. Document the test coverage in `specs/088-multilingual-repository-readme/contracts/parity-check-test-coverage.md` (NEW file) as the regression-prevention contract for future feature 089's docs-tree-link updates.

### Drift-issue auto-creator helper

- [X] T017 [W13B] Create `scripts/open-or-update-drift-issue.sh` (NEW) — a small bash helper invoked by the CI workflow's failure step per plan.md design Track B CI integration sketch. The script accepts a PR number argument; calls `gh issue list --label "readme-translation-drift" --state open` to find existing tracking issues; if found, updates the existing issue's body with the new PR reference + new diff; if not found, creates a new issue titled `README translation drift: PR #{N}` with the diff body + 7-day grace deadline timestamp + a link to the offending PR per spec SC-009. The script is idempotent — re-running it does NOT create duplicate issues.

### CI integration

- [X] T018 [W13B] Modify `.github/workflows/ci.yml` per plan.md correction §1 + §7 + design Track B sketch: (a) add the `readme: ['README*.md']` filter to the existing `dorny/paths-filter@v3` block at lines 25-43 (per T002 inventory); (b) add a new top-level `permissions:` block change adding `issues: write` AND `pull-requests: write` (the existing top-level permissions has `contents: read, packages: read, security-events: write` — UPD-038 ADDS to this, not replaces); (c) add a new job `readme-parity` after the existing lint jobs that runs `if: needs.changes.outputs.readme == 'true'`; the job checks out, sets up Python 3.12, installs pandoc via `sudo apt-get install -y pandoc`, runs `python scripts/check-readme-parity.py --pr-number ${{ github.event.pull_request.number }}`, and on failure invokes `scripts/open-or-update-drift-issue.sh` (T017).
- [ ] T019 [W13B] Verify the CI integration on a smoke-test PR per plan.md risk-register row 7: open a draft PR touching only `README.md` (no localized variants exist yet at this point, so the parity check naturally fails with "missing locale files" — exit code 2). Verify (a) the `readme-parity` job runs only when `README*.md` paths change; (b) the job has `issues: write` and `pull-requests: write` permissions; (c) the failure step invokes `open-or-update-drift-issue.sh` and creates a tracking GitHub issue. Close the smoke-test PR without merging; close the auto-created issue.
- [X] T020 [W13B] Wire the PR-comment posting per spec User Story 3 acceptance scenario 1: when the parity check exits with code 1 OR 2, the CI workflow posts a comment on the offending PR with the diff (the script's stdout). The comment uses GitHub's `gh pr comment` subprocess invocation in the workflow's failure step. The comment is updated (NOT duplicated) on subsequent CI runs of the same PR — uses `gh pr comment --edit-last` if available, else creates a new comment per run.

### `docs-translation-exempt` label + 30-day backfill follow-up

- [X] T021 [W13B] Create the `docs-translation-exempt` GitHub label per plan.md design + spec edge-case "Emergency security disclosure": label colour red (#d73a4a), description "Exempts the PR from the README parity check; requires 30-day backfill follow-up issue per FR-602". The label is created via `gh label create` (one-off setup task — documented in the contracts file but the label itself lives in GitHub repo config, not in the codebase).
- [X] T022 [W13B] Implement the 30-day backfill follow-up issue creation per spec User Story 3 acceptance scenario 4 + plan.md correction §1: when the parity check detects drift AND the `docs-translation-exempt` label is applied, the script (or the CI workflow's failure step) auto-creates a follow-up GitHub issue titled `README translation backfill (30-day SLA): PR #{N}` with the deadline 30 days from the PR merge timestamp. The issue is labelled `readme-translation-backfill` for filterable tracking. Add the label-creation step to T021's documentation.

---

## Phase 4: User Story 1 — First-Time Visitor (P1) 🎯 MVP VERIFICATION

**Story goal**: A first-time visitor reading the canonical English README in 2 minutes can answer "what is Musematic?", "for whom?", "what is the quick-start command?", "where do I find detailed docs?". The MVP — every other US (US2, US3) layers on top.

### Tests

- [ ] T023 [P] [US1] [W13D] Add an end-to-end usability test per spec SC-002: recruit 5 fresh evaluators (engineers, product managers, or similar — NOT contributors to this codebase); ask each to read the canonical English README on the GitHub-rendered Markdown view for ≤ 2 minutes; record their answers to the 4 SC-002 questions ("what is Musematic?", "for whom?", "what is the quick-start command?", "where do I find detailed docs?"). At least 4 of 5 evaluators MUST answer all 4 questions correctly within the 2-minute budget. Record the results in `specs/088-multilingual-repository-readme/contracts/usability-test-results.md` (NEW file).
- [X] T024 [P] [US1] [W13D] Add a parity-check exit-0 verification per SC-007: with all 6 READMEs in place (after Phase 5 translations land), run `python scripts/check-readme-parity.py` against the repo root; assert exit code 0 (parity); assert no diff is emitted to stdout; assert pandoc rendering of every variant succeeds. This task is gated on Phase 5 completion (T028-T032 must land first).

---

## Phase 5: Track C — Translations (5 Locales)

**Story goal**: 5 localized README variants delivered by the existing translation vendor + native-speaker reviewed; language-switcher byte-equivalence preserved.

### Vendor commission + delivery

- [ ] T025 [W13C] Submit the canonical English `README.md` (T009) + the canonical content text from T006's contracts file to the translation vendor with the 5 target locales: Spanish (neutral Latin American per plan.md research R6), Italian, German, French (France), Simplified Chinese. The vendor's 7-day SLA starts at submission per plan.md cross-feature coordination + spec assumption. The submission includes (a) the canonical content; (b) the language-switcher bar's byte-identical Markdown (do NOT translate); (c) the badges' Markdown (do NOT translate); (d) commands and code blocks marked DO-NOT-TRANSLATE (e.g., `make dev-up`, `git clone`, file paths) per spec edge-case + FR-603; (e) the architecture diagram is shared (do NOT request translation per FR-603). Track the vendor engagement in `specs/088-multilingual-repository-readme/contracts/translation-vendor.md` (T003) with the submission timestamp + expected delivery date.
- [ ] T026 [P] [W13C] Receive the 5 translated files from the vendor; place them at the repo root as `README.es.md`, `README.it.md`, `README.de.md`, `README.fr.md`, `README.zh.md`. Each file MUST have the byte-identical language-switcher bar (per T008 + spec edge-case "Language switcher byte-equivalence"). Verify the language-switcher byte-equivalence by running the parity-check script in dry-run mode (`python scripts/check-readme-parity.py --pr-number 0` — exit code 0 expected for the bar check; other parity issues handled in subsequent tasks).

### Per-locale verification (parallelizable)

- [X] T027 [P] [W13C] Verify `README.es.md` per the parity-check script: run `python scripts/check-readme-parity.py` and inspect the output for any drift between the canonical English and the Spanish variant; if drift is detected (e.g., heading count mismatch — likely from translation expanding/contracting headings), file the diff back to the vendor for revision. Iterate until exit code 0.
- [X] T028 [P] [W13C] Same as T027 for `README.it.md` (Italian).
- [ ] T029 [P] [W13C] Same as T027 for `README.de.md` (German). Special attention: umlauts (ö, ü, ä) MUST render correctly on GitHub per plan.md risk-register row 9; the parity check verifies via pandoc but a manual visual check on the GitHub-rendered preview is also performed.
- [X] T030 [P] [W13C] Same as T027 for `README.fr.md` (French — France).
- [ ] T031 [P] [W13C] Same as T027 for `README.zh.md` (Simplified Chinese). Special attention: Chinese characters MUST render correctly on GitHub per plan.md risk-register row 9; UTF-8 BOM is omitted per Markdown convention; the file is encoded as UTF-8 without BOM.

### Native-speaker review (US2 verification)

- [X] T032 [W13C] Run the parity-check script against all 6 files post-translation: `python scripts/check-readme-parity.py --pr-number {PR}`; assert exit code 0; assert no drift detected. If any drift remains, iterate with the vendor (T026) until clean.

---

## Phase 6: User Story 2 — Spanish-Speaking Evaluator + Native-Speaker Quality (P1)

**Story goal**: Each of the 5 localized variants achieves a native-speaker quality rating ≥ 4/5 per SC-003. Quality is a HUMAN gate — NOT enforced by the CI script per spec User Story 2 acceptance scenarios.

### Reviews (parallelizable across locales)

- [ ] T033 [P] [US2] [W13D] Recruit a native-speaker reviewer per locale per plan.md research R10 + spec assumption. Reviewers may be internal staff, community contributors, or vendor QA. Send each reviewer the corresponding `README.{lang}.md` file via the contracts/translation-quality-reviews.md file template; ask each to (a) read the file top-to-bottom; (b) rate translation quality on a 1-5 scale; (c) flag any awkward phrasings or technical inaccuracies; (d) verify all 11 FR-601 sections are present; (e) verify the language-switcher bar links work. Record the reviews in `specs/088-multilingual-repository-readme/contracts/translation-quality-reviews.md` per SC-003.
- [ ] T034 [P] [US2] [W13D] Iterate with the vendor on any locale rated < 4/5: send back the reviewer's feedback; receive the revised file; re-run the parity-check; re-submit to the reviewer. Repeat until each locale rates ≥ 4/5.

---

## Phase 7: User Story 3 — Translation Drift Detection (P2)

**Story goal**: The parity-check script + CI integration + drift-issue auto-creator + `docs-translation-exempt` label override + grace-window logic work end-to-end on a synthetic test PR.

### End-to-end verification

- [ ] T035 [US3] [W13D] Author a synthetic test PR per spec User Story 3 acceptance scenarios + spec independent test: (a) add a new H2 section to `README.md` only (do NOT update the 5 localized variants); (b) push the branch; (c) verify the CI parity-check job runs and exits with code 1 (warning); (d) verify the auto-created GitHub tracking issue is created with title `README translation drift: PR #{N}`; (e) verify the PR receives a comment with the diff per T020; (f) close the test PR without merging; close the auto-created issue.
- [ ] T036 [P] [US3] [W13D] Verify the `docs-translation-exempt` label override per spec User Story 3 acceptance scenario 4: re-author the synthetic PR from T035; apply the `docs-translation-exempt` label; verify the parity-check exits with code 1 (warning, downgraded) instead of 2 (hard fail); verify a 30-day-backfill follow-up issue is auto-created per T022. Close the test PR without merging.
- [ ] T037 [P] [US3] [W13D] Verify the 7-day grace window expiry per spec User Story 3 acceptance scenario 3 + plan.md research R4: temporarily reduce `GRACE_WINDOW` in the parity-check script to 1 minute (a config override via env var `MUSEMATIC_README_GRACE_OVERRIDE_SECONDS=60`); author a fresh synthetic drift PR; wait 2 minutes; trigger a new CI run on a subsequent PR touching `README*.md`; verify the parity-check exits with code 2 (hard fail). Restore `GRACE_WINDOW` to 7 days; close the test artifacts.

### Single-locale typo-fix exemption

- [ ] T038 [P] [US3] [W13D] Verify the typo-fix-doesn't-trigger-drift behaviour per spec User Story 3 acceptance scenario 5 + spec edge-case "Translation typo fix": author a synthetic PR touching ONLY `README.es.md` (e.g., correcting a typo); verify the parity-check exits with code 0 (NOT flagged as drift); the parity-check counts only NEW headings, NEW badges, NEW links — not arbitrary content edits within an existing section. Close the test PR.

---

## Phase 8: External Link Validation (Weekly Workflow)

**Story goal**: External links (shields.io, GitHub Issues, Discussions, etc.) are validated weekly per spec edge-case + plan.md research R5. Failures open a tracking issue; do NOT block any PR.

### Weekly workflow + config

- [X] T039 [W13D] Create `.github/workflows/docs-external-links.yml` per plan.md design Track B + research R5: schedule trigger `cron: '0 6 * * 0'` (Sundays 6am UTC) plus `workflow_dispatch` for manual runs; permissions `contents: read, issues: write`; one job that checks out the repo, installs `markdown-link-check` via `npx --yes` (no new repo dep), runs the link-check on all 6 `README*.md` files via `npx --yes markdown-link-check README*.md --config .github/markdown-link-check.json`. On failure, the workflow runs `gh issue create --title "External link rot detected in READMEs" --body "..." --label docs,external-link-rot` per the design's failure-step pattern.
- [X] T040 [P] [W13D] Create `.github/markdown-link-check.json` (NEW config file) per plan.md design: configures `markdown-link-check` to (a) ignore relative file links (those are validated by the per-PR parity check, not here); (b) validate external HTTP/HTTPS links; (c) retry transient failures up to 3 times with exponential backoff; (d) use a 30-second timeout per request; (e) ignore `localhost` URLs and `example.com` placeholders.

---

## Phase 9: Finalization

**Story goal**: GitHub render verification + GitLab compatibility check + pandoc / MkDocs rendering + release announcement per plan.md Track D phase.

- [ ] T041 [W13D] Verify GitHub renders all 6 variants correctly per FR-604 + plan.md risk-register rows 8-9: navigate to each `README*.md` file's GitHub page; verify (a) badges render; (b) language-switcher bar renders inline; (c) architecture diagram renders inline; (d) Chinese characters in `README.zh.md` render correctly (no `?` or empty boxes); (e) German umlauts in `README.de.md` render correctly; (f) all internal links are clickable. Capture screenshots of each variant for the contracts/usability-test-results.md (T023).
- [ ] T042 [P] [W13D] Verify mobile rendering on the GitHub mobile app per plan.md risk-register row 8: open each `README*.md` file on the GitHub iOS or Android app; verify the language-switcher bar wraps acceptably on narrow viewports (NOT into a single line of unreadable density). If the bar wraps awkwardly, T008's bar Markdown is updated with explicit line breaks between locale blocks AND T028-T032 (translations) re-run the parity check on the updated bar.
- [X] T043 [P] [W13D] Verify pandoc rendering per FR-604 + SC-012: locally install pandoc; run `pandoc -f gfm -t html README.md > /tmp/check.html` for each variant; assert zero parser errors; spot-check the HTML output renders the architecture diagram via the SVG `<img>` tag.
- [X] T044 [P] [W13D] Verify MkDocs rendering per FR-604: the on-disk `mkdocs.yml` (verified per inventory) is the existing platform docs site config; verify it can include the README files (e.g., via `nav:` block) without breaking — this is informational; UPD-038 does NOT change `mkdocs.yml` (that's feature 089's scope).
- [ ] T045 [W13D] Publish a release announcement mentioning multilingual README availability per plan.md Track D phase 4 + brownfield input's "Publish release announcement". The announcement (a small entry in `CHANGELOG.md` AND a brief GitHub Discussions post) credits the translation vendor + native-speaker reviewers, links to all 6 README files, notes the 7-day SLA + drift-detection workflow.

---

## Phase 10: Polish + Cross-Feature Coordination

- [X] T046 [P] [W13D] Update `CLAUDE.md` (project root) per the speckit convention: append "Recent Changes" with a 1-2 line summary of UPD-038's contributions; record the 12 brownfield-input corrections from plan.md correction list as future-planner reference for feature 089 / UPD-039 (which will reorganize the docs tree and update README links). Keep the file under the 200-line rule.
- [ ] T047 [W13D] Cross-feature coordination follow-up: confirm with feature 089 / UPD-039's owner that UPD-038's documentation-index links (T009 §9) point to the on-disk tree TODAY and will be updated as part of UPD-039's reorganization PR per plan.md correction §2 + cross-feature coordination matrix. Record the sign-off in this task's commit message.
- [X] T048 [W13D] Author the operator README addendum at `specs/088-multilingual-repository-readme/quickstart.md` (NEW): a small operator-focused walkthrough explaining how to (a) add a new section to the canonical English README; (b) submit the diff to the translation vendor; (c) handle the 7-day grace window + drift-tracking issue lifecycle; (d) apply the `docs-translation-exempt` label for emergency disclosures. This is the contributor-facing companion to FR-602.
- [ ] T049 [W13D] Run the full E2E verification: with all 6 READMEs in place + `docs/assets/architecture-overview.svg` + `scripts/check-readme-parity.py` + tests + CI integration + weekly workflow + label, verify (a) the parity-check script exits with code 0 on the canonical state per SC-007; (b) the CI step runs and passes on a no-op PR touching `README*.md`; (c) the weekly workflow runs once on `workflow_dispatch` and reports zero external link failures; (d) all 6 variants render correctly on GitHub + pandoc + MkDocs per FR-604. Document the verification in this task's commit message.

---

## Task Count Summary

| Phase | Range | Count | Wave | Parallelizable |
|---|---|---|---|---|
| Phase 1 — Setup | T001-T003 | 3 | W13.0 | partially |
| Phase 2 — Track A Canonical English + diagram | T004-T010 | 7 | W13A | mostly sequential |
| Phase 3 — Track B Parity-check script + CI | T011-T022 | 12 | W13B | mostly sequential |
| Phase 4 — US1 P1 MVP verification | T023-T024 | 2 | W13D | yes |
| Phase 5 — Track C Translations (5 locales) | T025-T032 | 8 | W13C | yes (5 locales parallel) |
| Phase 6 — US2 P1 native-speaker quality | T033-T034 | 2 | W13D | yes |
| Phase 7 — US3 P2 drift-detection E2E | T035-T038 | 4 | W13D | yes |
| Phase 8 — External link validation (weekly) | T039-T040 | 2 | W13D | yes |
| Phase 9 — Finalization | T041-T045 | 5 | W13D | mostly parallel |
| Phase 10 — Polish + coordination | T046-T049 | 4 | W13D | yes |
| **Total** | | **49** | | |

## MVP Definition

**The MVP is US1 (Phase 2 — canonical English `README.md` + architecture diagram + Phase 4 usability verification).** Without US1, the platform's GitHub presence is invisible to first-time visitors. After US1 lands, US2 (5 localized variants) and US3 (parity-check CI gate) are the next P1 / P2 must-haves; the weekly external link validation is a quality-of-life add.

## Dependency Notes

- **T001-T003 (Setup) → all phases**: inventory verification + CI plan + vendor engagement are upstream of every track.
- **T004-T010 (Track A canonical English) → US1 verification + Track C translations**: the canonical English is the source of truth; the vendor cannot translate without it.
- **T011-T022 (Track B parity-check + CI) → US3 verification + US1 SC-007 verification**: the script must exist + run in CI before drift detection can be tested.
- **T025-T032 (Track C translations) → US2 verification + final parity-check exit 0**: the 5 localized files must exist before native-speaker reviews + final parity-check pass.
- **T033-T034 (US2 native-speaker reviews) → SC-003 ≥ 4/5 quality rating**: parallelizable across locales; iterate with vendor on misses.
- **T039-T040 (weekly external-link workflow) → independent**: can land in parallel with any other phase; does NOT block US1 / US2 / US3.
- **Feature 089 / UPD-039 reorganizes docs**: T009's documentation-index links match TODAY's tree; UPD-039 updates them in its own PR.
- **Feature 083 / UPD-030 translation-vendor relationship**: precondition for T025-T032; T003 verifies.

## Constitutional Audit Matrix

| Constitution rule / FR | Verified by | Phase |
|---|---|---|
| FR-600 — 6 READMEs at repo root | T009 (English) + T026 (5 localized) + T032 final parity check | Phase 2 + 5 |
| FR-601 — 11-section structure | T009 follows the canonical order; T011 parity-check verifies via heading extraction | Phase 2 + 3 |
| FR-602 — translation drift CI gate + 7-day grace | T011-T022 implement the script + CI + label override | Phase 3 |
| FR-603 — language-neutral assets | T005 single shared SVG; T011 parity-check verifies diagram path byte-equivalence across variants | Phase 2 + 3 |
| FR-604 — cross-renderer rendering (GitHub + GitLab + pandoc + MkDocs) | T041 + T043 + T044 verification; T011 parity-check invokes pandoc per file | Phase 9 |
| Wave 13 placement | All tasks tagged W13.0 / W13A / W13B / W13C / W13D | All |
