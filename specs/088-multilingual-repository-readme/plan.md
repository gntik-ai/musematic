# Implementation Plan: UPD-038 — Multilingual Repository README

**Branch**: `088-multilingual-repository-readme` | **Date**: 2026-04-27 | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

## Summary

UPD-038 is the smallest feature in the v1.3.0 cohort by surface area: it ships **6 README files** at the repo root (the GitHub default `README.md` plus 5 localized variants in Spanish / Italian / German / French / Simplified Chinese), **one CI parity-check script** at `scripts/check-readme-parity.py`, **one architecture-diagram asset** at `docs/assets/architecture-overview.svg` (a NEW directory — does NOT exist on disk per inventory), and **two CI integrations** (a parity-check step inside the existing `.github/workflows/ci.yml` running on every PR touching `README*.md`, plus a NEW weekly-scheduled workflow for external link validation). It is delivered in three convergent tracks:

- **Track A — Content** (~0.5 dev-day for canonical English): write the canonical English `README.md` following the FR-601 11-section structure, create the architecture diagram + the new `docs/assets/` directory, set up the shields.io badges, draft the tagline + "What is Musematic?" section.
- **Track B — Tooling** (~0.5 dev-day): author `scripts/check-readme-parity.py` (Python stdlib only — no new deps; compares H1/H2/H3 headings + badge count + link count + language-switcher-bar byte-equivalence + invokes `pandoc` for cross-renderer validation per FR-604); integrate into `.github/workflows/ci.yml` (existing paths-filter at `dorny/paths-filter@v3` already supports a `readme: ['README*.md']` filter — UPD-038 adds it); implement the 7-day grace window via GitHub issue creation date; implement the `docs-translation-exempt` label-based bypass; create a separate weekly-scheduled workflow for external link validation.
- **Track C — Translations** (~1 dev-day, dependent on the translation vendor's 3-5-day SLA): commission translations for the 5 target locales via the existing translation vendor (the same vendor feature 083 / UPD-030 uses for UI strings — reuse, do not introduce a new vendor); native-speaker review per locale (the precondition is reviewer availability per spec assumptions); commit the 5 translated files; verify the language-switcher bar is byte-identical across all 6 variants; run the parity-check script and fix any detected drift.

The three tracks converge in Phase 4 for finalization: verify GitHub renders all 6 variants correctly (including Chinese characters and umlauts), verify mobile rendering on the GitHub mobile app, verify pandoc / MkDocs rendering for eventual export per FR-604, publish a release announcement.

## Constitutional Anchors

This plan is bounded by the following Constitution articles. Each implementation step below cites the article it serves.

| Anchor | Citation | Implementation tie |
|---|---|---|
| **UPD-038 declared** | Constitution line 8 (audit-pass roster) | The whole feature |
| **FR-600 — 6 README variants** | FR doc lines 2213-2214 | T009 (canonical English) + T024-T028 (5 localized variants) |
| **FR-601 — 11-section structure** | FR doc lines 2216-2228 | T009 follows the canonical 11-section order; T031 parity check verifies via H1/H2/H3 match |
| **FR-602 — translation drift CI gate + 7-day grace** | FR doc lines 2230-2231 | T015-T020 implement the script; T032 wires the GitHub-issue auto-creator |
| **FR-603 — language-neutral assets** | FR doc lines 2233-2234 | T010 creates ONE shared architecture diagram in English; UI screenshots OPTIONAL per locale |
| **FR-604 — cross-renderer rendering** | FR doc lines 2236-2237 | T037 verifies pandoc/MkDocs rendering; T031 parity script invokes `pandoc -f gfm -t html` per file |

## Technical Context

| Item | Value |
|---|---|
| **Languages** | Markdown (the 6 README files), Python 3.12 (the parity-check script — stdlib only), YAML (CI workflow additions). No application-code changes. |
| **Primary Dependencies (existing — reused)** | shields.io (external — for the 4 badges); the existing `gh` CLI (already available in GitHub Actions runners — no new dependency); `pandoc` (installed via `apt-get install pandoc` in the workflow step — small footprint); the existing `dorny/paths-filter@v3` action at `.github/workflows/ci.yml` (verified per inventory). |
| **Primary Dependencies (NEW in 088)** | None — the parity-check script uses Python stdlib only (`re`, `pathlib`, `subprocess`, `argparse`, `json`); pandoc is installed via apt in the workflow step. |
| **Storage** | None. UPD-038 owns no database tables, no Redis keys, no Kafka topics, no PostgreSQL migrations. The 6 README files live as Markdown in the repo root; the architecture diagram lives in the new `docs/assets/` directory. |
| **Testing** | The parity-check script has its own pytest test file at `scripts/tests/test_readme_parity.py` covering: drift detection (exit 1), no-drift case (exit 0), grace-window expiry (exit 2 after 7 days), exempt label (exit 0 with warning), language-switcher-bar byte-equivalence, link-count mismatch detection. The translation quality is a HUMAN gate per spec SC-003 — NOT a CI test. |
| **Target Platform** | Markdown rendered by: GitHub (canonical), GitLab (compatibility — verified by FR-604), pandoc (cross-renderer fallback), MkDocs (the existing platform docs site — verified by `mkdocs.yml` at the repo root per inventory). |
| **Project Type** | Documentation feature with light tooling. No application code, no infrastructure, no migrations. |
| **Performance Goals** | Parity-check script execution adds < 30 s to every PR's CI duration per SC-013; the weekly external-link-validation workflow runs in < 5 minutes. |
| **Constraints** | FR-602 7-day grace window for translation drift (after 7 days, hard fail unless `docs-translation-exempt` label applied); FR-603 architecture diagrams are language-neutral (shared across all 6 variants); FR-604 cross-renderer compatibility (GitHub + GitLab + pandoc + MkDocs). |
| **Scale / Scope** | Track A: 1 canonical English README + 1 architecture diagram + 1 new `docs/assets/` directory. Track B: 1 Python script (~ 200 lines) + 1 CI workflow modification + 1 NEW weekly workflow. Track C: 5 localized README files via the translation vendor (out-of-band wall-clock SLA). Total: 6 README files + 1 SVG + 1 Python script + 2 workflow integrations. |

## Constitution Check

> **GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.**

| Check | Verdict | Rationale |
|---|---|---|
| Brownfield rule — modifications respect existing repo discipline | ✅ Pass | UPD-038 adds 6 files at the repo root + 1 new `docs/assets/` directory + 1 script under `scripts/` + 1 CI workflow modification + 1 NEW weekly workflow. No application-code changes. |
| FR-600 + FR-601 — 6 READMEs + 11-section structure | ✅ Pass | T009 + T024-T028 deliver 6 files; T009's H2 headings strictly match FR-601's enumeration. |
| FR-602 — 7-day grace window + GitHub-issue tracking | ✅ Pass | T015-T020 + T032 implement the gate. |
| FR-603 — language-neutral assets | ✅ Pass | T010 creates ONE shared architecture diagram; T031 parity-check verifies the diagram path is byte-identical across all 6 variants. |
| FR-604 — cross-renderer compatibility | ✅ Pass | T031 invokes `pandoc -f gfm -t html` on each variant; T037 manually verifies GitLab rendering before merge. |
| Translation-vendor reuse from feature 083 / UPD-030 | ✅ Pass (assumption) | Per spec assumptions — the vendor relationship is a precondition. |
| Native-speaker reviewer availability | ✅ Pass (assumption) | Per spec assumptions — reviewer recruitment is a precondition. |

**Verdict: gate passes. No declared variances. UPD-038 is the smallest constitutional feature in the v1.3.0 cohort.**

## Project Structure

### Documentation (this feature)

```text
specs/088-multilingual-repository-readme/
├── plan.md                # this file
├── spec.md
├── planning-input.md
└── tasks.md               # produced by /speckit.tasks (next phase)
```

### Source Code (repository root) — files this feature creates or modifies

```text
README.md                                    # NEW (canonical English; ~150-300 lines per FR-601's 11 sections)
README.es.md                                 # NEW (Spanish — neutral Latin American per spec assumption)
README.it.md                                 # NEW (Italian)
README.de.md                                 # NEW (German)
README.fr.md                                 # NEW (French — France)
README.zh.md                                 # NEW (Simplified Chinese)

docs/
├── assets/                                  # NEW directory (does not exist on disk per inventory)
│   └── architecture-overview.svg            # NEW (single high-level diagram, English-labeled per FR-603)
├── administration/                          # already on disk; UPD-038 links to it
├── development/                             # already on disk; UPD-038 links to it
├── features/                                # already on disk
├── integrations/                            # already on disk
├── operations/                              # already on disk
└── (top-level files: agents.md, FR doc, system-architecture-v5.md, software-architecture-v5.md — all already on disk)

scripts/
├── ci/                                      # already on disk
├── check-readme-parity.py                   # NEW (~200 lines Python stdlib only)
└── tests/
    └── test_readme_parity.py                # NEW (~150 lines pytest unit tests for the parity-check script)

.github/workflows/
├── ci.yml                                   # MODIFY (add `readme-parity` job; uses existing dorny/paths-filter@v3 with new `readme: ['README*.md']` filter)
├── docs-external-links.yml                  # NEW (separate weekly-scheduled workflow per spec edge-case)
├── build-cli.yml                            # NO CHANGE
├── deploy.yml                               # NO CHANGE
├── e2e.yml                                  # NO CHANGE
└── sdks.yml                                 # NO CHANGE
```

**Structure Decision**: UPD-038 adds 6 Markdown files at the repo root (sibling to existing `AGENTS.md`, `CHANGELOG.md`, `Makefile`, etc.), one new `docs/assets/` directory with a single SVG, one Python script with its test, and two CI workflow changes (one modification + one new file). No application code, no migrations, no new BC.

## Brownfield-Input Reconciliations

These are corrections from spec to plan. Each is an artifact-level discrepancy between the brownfield input and the on-disk codebase.

1. **The brownfield input proposes `.github/workflows/docs.yml` as the home for the parity check.** The on-disk inventory confirms `.github/workflows/` has 5 existing workflows (`build-cli.yml`, `ci.yml`, `deploy.yml`, `e2e.yml`, `sdks.yml`) — NO `docs.yml`. **Resolution:** UPD-038 ADDS the parity-check job inside the existing `ci.yml` workflow (per spec scope discipline) using the existing `dorny/paths-filter@v3` action's pattern; T020 also creates a NEW separate workflow at `.github/workflows/docs-external-links.yml` for the WEEKLY external-link validation (per spec edge-case "external link rot" — this MUST be a separate workflow because it runs on a `schedule:` trigger, not on PR). The brownfield's "docs.yml" wording is corrected: there is no single `docs.yml`; the work splits across `ci.yml` (per-PR) and `docs-external-links.yml` (weekly).

2. **The brownfield template's documentation index links do NOT match the on-disk `docs/` tree.** Verified: brownfield template references `./docs/user-guide/`, `./docs/admin-guide/`, `./docs/operator-guide/`, `./docs/developer-guide/`, `./docs/api/`, `./docs/architecture/`. The on-disk `docs/` tree has subdirectories `administration/`, `development/`, `features/`, `integrations/`, `operations/`. **Resolution:** T009's documentation-index section uses links matching the on-disk tree TODAY (e.g., `[Administration Guide](./docs/administration/)`, `[Operations Guide](./docs/operations/)`, `[Development Guide](./docs/development/)`, `[Features](./docs/features/)`, `[Integrations](./docs/integrations/)`, `[System Architecture](./docs/system-architecture-v5.md)`, `[Software Architecture](./docs/software-architecture-v5.md)`, `[Functional Requirements](./docs/functional-requirements-revised-v6.md)`). Feature 089 / UPD-039 will reorganize per FR-605 — at that point, the README links are updated as part of UPD-039's scope (the inverse of the brownfield's "either UPD-039 is merged first OR README links are placeholders" — UPD-038 ships valid links to today's tree, UPD-039 reorganizes-and-updates).

3. **The brownfield template references `./docs/getting-started.md` and `./docs/install/{kind,k3s,hetzner,managed}.md` — none exist on disk.** Verified: no `getting-started.md` at `docs/` root; no `install/` subdirectory. **Resolution:** T009's quick-start section's "See the [Getting Started Guide](./docs/getting-started.md)" link is replaced with "See the [development guide](./docs/development/) for a walkthrough" pointing to the existing on-disk directory. T009's installation-options table references the corresponding deploy/helm guides (e.g., `[Install on kind](./deploy/helm/observability/README.md)` from feature 085 / UPD-035 if it exists, otherwise pointing to `./docs/operations/` as the closest on-disk fallback). The plan phase verifies what's on disk at the moment of authoring; the spec captures the requirement that EVERY link MUST resolve to an existing file (per SC-006 internal-link-validity contract — broken local links warn but don't fail until the referenced files exist).

4. **The brownfield template's architecture diagram path `./docs/assets/architecture-overview.svg` does NOT exist on disk.** Verified: no `docs/assets/` directory. **Resolution per plan correction §4 of the spec:** T010 creates the `docs/assets/` directory + a placeholder SVG (~ 30-50 element diagram showing control plane + Go satellites + data stores + Kafka + observability stack — the canonical "control-plane + satellite-services" topology described in the brownfield template's architecture paragraph). The placeholder uses inline SVG primitives (no external font or image dependencies) so it renders consistently on GitHub, GitLab, and pandoc. Feature 089 / UPD-039 may replace the placeholder with a polished version; UPD-038 ships a serviceable starter.

5. **`make dev-up` quick-start command verified at `Makefile:38-41`.** The target delegates to `tests/e2e/Makefile`'s `e2e-up` target. UPD-038's quick-start uses `make dev-up` AS-IS — no changes.

6. **GitHub repo URL `gntik-ai/musematic`** verified per the recent PR merge commits.

7. **`.github/workflows/ci.yml`'s existing paths-filter pattern** (verified at lines 25-43 per inventory) uses `dorny/paths-filter@v3` to detect changed paths. UPD-038 adds a new filter:
```yaml
readme:
  - 'README*.md'
```
   The new `readme-parity` job runs only when this filter outputs true. This avoids the parity check running on every PR (which would be wasteful since most PRs don't touch the READMEs).

8. **The `gh` CLI** is pre-installed on GitHub Actions `ubuntu-latest` runners — no installation step needed. The parity-check script's GitHub-issue auto-creator uses `gh issue create` (subprocess invocation) authenticated via `GITHUB_TOKEN`. The workflow's `permissions:` block needs `issues: write` added.

9. **pandoc installation in CI**: the `pandoc` binary is NOT pre-installed on `ubuntu-latest` runners. T020 adds an `apt-get install -y pandoc` step before the parity-check script runs. The pandoc invocation is `pandoc -f gfm -t html /dev/null` to validate Markdown → HTML conversion per file; failures indicate cross-renderer incompatibility per FR-604.

10. **The brownfield's "5-minute path to running install"** (Quick Start section) refers to `make dev-up` which delegates to `tests/e2e/Makefile`'s `e2e-up` target. This target's actual execution time depends on Docker image pull speed — typical wall-clock is 3-7 minutes on first run, 30-60 seconds on subsequent runs (warm cache). The README's "5 minutes" claim is the steady-state — first runs MAY be slower; T009's quick-start text adds a clarifying note.

11. **Translation vendor + workflow.** The brownfield says "same workflow as UPD-030 for the UI" — feature 083 / UPD-030's translation-vendor pipeline is a precondition. The plan phase verifies the vendor relationship exists; if not, T024-T028 (the 5 localized files) are blocked until the vendor is engaged. The plan does NOT introduce a NEW vendor.

12. **Native-speaker reviewer process.** Per spec SC-003 + assumptions, native-speaker reviewers rate each localized variant on a 1-5 scale. The reviewer-recruitment process is OUT OF SCOPE; the plan assumes reviewers are available. If reviewers cannot be recruited for a locale, the affected variant ships without quality validation — flagged as a follow-up.

## Phase 0 — Research and Design Decisions

### R1. Documentation-tree links — match on-disk vs. placeholder

The on-disk `docs/` tree (`administration/`, `development/`, `features/`, `integrations/`, `operations/` + 4 top-level `.md` files) does NOT match the brownfield template's structure (`user-guide/`, `admin-guide/`, etc.).

**Decision**: Match the on-disk tree TODAY. Reasons: (a) the FR-606+ documentation reorganization is feature 089's scope; (b) every UPD-038 link MUST resolve at merge time per SC-006 (broken links warn but don't fail in this feature's CI); (c) when feature 089 reorganizes, it updates the READMEs in the same PR — same-feature consistency is preserved.

### R2. Architecture diagram — create new placeholder vs. inline text

The brownfield template references `./docs/assets/architecture-overview.svg`; the file does NOT exist.

**Decision**: Create a placeholder SVG. Reasons: (a) inline-text architecture descriptions don't render well on GitHub's mobile app; (b) a serviceable starter diagram (~ 30-50 elements showing control plane + satellites + data stores + Kafka + observability stack) is < 4 hours of work; (c) feature 089 may replace with a polished version. T010 creates the SVG; the format choice (inline `<svg>` primitives, no external font) ensures consistency across renderers per FR-604.

### R3. Parity-check script — Python stdlib vs. external Markdown library

The parity-check needs to extract H1/H2/H3 headings from Markdown, count badges, count links, and validate cross-renderer compatibility.

**Decision**: Python stdlib only (`re`, `pathlib`, `subprocess`, `argparse`, `json`). Reasons: (a) no new repo dependency to maintain; (b) Markdown's heading syntax (`^#{1,3} `) and link syntax (`\[.+?\]\(.+?\)`) are simple enough for regex; (c) cross-renderer validation delegates to `pandoc` via subprocess (the canonical Markdown reference renderer). The `pandoc` binary is installed via apt in the CI workflow step.

### R4. 7-day grace window timing source — git history vs. GitHub issue creation date

FR-602's 7-day grace window starts when drift is detected. Two timing sources:
1. The PR's merge timestamp (read via `git log --merges`).
2. The GitHub-issue creation timestamp (read via `gh api`).

**Decision**: GitHub issue creation timestamp. Reasons: (a) the auto-created issue is the canonical record per spec User Story 3 acceptance scenario 2; (b) `gh api` is straightforward; (c) git-history-based timing breaks if the repo is rebased or force-pushed.

### R5. Weekly external link validation — separate workflow vs. extension to existing scheduled

The spec edge-case "external link rot" requires weekly validation; the existing CI workflows have no weekly schedule.

**Decision**: NEW workflow `docs-external-links.yml` at `.github/workflows/`. Reasons: (a) external link checks are slow (5+ minutes) and would add noise to the existing CI workflows; (b) a dedicated workflow with `schedule: cron: '0 6 * * 0'` (Sundays 6am UTC) is the canonical pattern; (c) the workflow opens a GitHub issue on failure (not a CI failure) — broken external links should not block any PR.

### R6. Locale order in the language-switcher bar

The bar lists 6 locales. Three ordering schemes:
1. Alphabetical (Deutsch, English, Español, Français, Italiano, 简体中文).
2. By population (English, 简体中文, Español, Français, Deutsch, Italiano).
3. By reading direction / language-family clusters (English, Español, Italiano, Français, Deutsch, 简体中文 — Latin/Romance, then Germanic, then East Asian).

**Decision**: Match the brownfield's order verbatim: English · Español · Italiano · Deutsch · Français · 简体中文. Rationale: this is the brownfield's chosen order; it groups Romance languages together; native English-speakers find their language first. The order is byte-identical across all 6 variants per the language-switcher-bar byte-equivalence requirement.

### R7. `gh issue create` authentication

The parity-check script's auto-creator runs in CI; needs to authenticate to the GitHub API.

**Decision**: Use the standard `GITHUB_TOKEN` available in every GitHub Actions workflow. The workflow's `permissions:` block adds `issues: write` AND `pull-requests: write` (for the PR comment per spec User Story 3 acceptance scenario 1). The script reads `GITHUB_TOKEN` from `os.environ` and passes it as the `--token` flag to `gh issue create` (or sets `GH_TOKEN` env var which `gh` reads automatically).

### R8. Cross-renderer validation — what does pandoc check?

`pandoc -f gfm -t html` converts GitHub-Flavored Markdown to HTML. It will fail on:
- Malformed link syntax (`[text](broken)`)
- Unclosed backtick code blocks
- Invalid Markdown table structure

**Decision**: T031 invokes `pandoc -f gfm -t html /dev/null < README.{lang}.md` per file; non-zero exit code is a parity-check failure per FR-604. Pandoc does NOT validate semantic correctness (a link to a non-existent file passes pandoc); local-file-link validation is a separate parity-check phase using `pathlib.Path.exists()`.

### R9. Markdown badges — static state vs. live shields.io

The brownfield template uses dynamic shields.io badges that fetch state from GitHub Actions / the GitHub API. Two patterns:
1. **Static badges** (hardcoded "passing" / "1.28+"): faster render, no external dependency.
2. **Dynamic badges** (live fetch from shields.io): always-current, requires shields.io availability.

**Decision**: Dynamic badges via shields.io. Reasons: (a) the build-status badge MUST be live (a stale "passing" badge is a quality regression signal); (b) shields.io is the de-facto standard for OSS README badges; (c) T031's parity check counts badge tags but does NOT fetch live state — the count check is sufficient for parity; the weekly external-link workflow (R5) catches shields.io itself going down.

### R10. Localized README quality reviewers

Per SC-003, each localized variant achieves a native-speaker quality rating ≥ 4/5. The reviewer process:
1. The translation vendor delivers the 5 files.
2. A native-speaker reviewer reads the variant top-to-bottom.
3. The reviewer files a review comment on the PR with a 1-5 rating.
4. If rating < 4, the variant is sent back to the vendor for revision (rinse + repeat).

**Decision**: Reviewers are recruited from internal staff first, then community contributors, then vendor QA pass. The reviewer's PR comment is captured in `specs/088-multilingual-repository-readme/contracts/translation-quality-reviews.md` (T036) per locale. The CI parity check does NOT enforce quality; quality is a human gate.

## Phase 1 — Design

### Track A — Canonical English README Structure

Per FR-601's 11-section enumeration, the canonical English `README.md` follows this exact order (matching the brownfield template):

```markdown
# Musematic — Agentic Mesh Platform

[![Build](...)] [![License]()] [![Kubernetes]()] [![Version]()]

> **Read this in other languages**: [English](./README.md) · [Español](./README.es.md) · [Italiano](./README.it.md) · [Deutsch](./README.de.md) · [Français](./README.fr.md) · [简体中文](./README.zh.md)

**Tagline + 1-paragraph description.**

---

## What is Musematic?
…
## Core capabilities
…
## Quick start
…
## Installation options
…
## Architecture at a glance
![Architecture diagram](./docs/assets/architecture-overview.svg)
…
## Documentation
- [Administration Guide](./docs/administration/)
- [Operations Guide](./docs/operations/)
- [Development Guide](./docs/development/)
- [Features Documentation](./docs/features/)
- [Integrations](./docs/integrations/)
- [System Architecture](./docs/system-architecture-v5.md)
- [Software Architecture](./docs/software-architecture-v5.md)
- [Functional Requirements](./docs/functional-requirements-revised-v6.md)

## Contributing
See [CONTRIBUTING.md](./CONTRIBUTING.md) — note: link is informational; the file may not yet exist per plan correction §2.

## License
See [LICENSE](./LICENSE) — note: link is informational; the file may not yet exist per plan correction §2.

## Community and support
- Issues: [GitHub Issues](https://github.com/gntik-ai/musematic/issues)
- Discussions: [GitHub Discussions](https://github.com/gntik-ai/musematic/discussions)
- Security disclosure: see [SECURITY.md](./SECURITY.md) — email `security@musematic.ai`
```

The 5 localized variants preserve the section order; only the prose is translated. The language-switcher bar is byte-identical across all 6 files per R6.

### Track B — `scripts/check-readme-parity.py` Architecture

```python
#!/usr/bin/env python3
"""README parity checker per FR-602.

Exit codes:
  0 — all 6 READMEs in parity
  1 — drift detected within the 7-day grace window (warning)
  2 — hard fail beyond the 7-day grace window or signature mismatch
"""
import argparse, json, os, re, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOCALES = ["", ".es", ".it", ".de", ".fr", ".zh"]  # canonical first
GRACE_WINDOW = timedelta(days=7)
LANGUAGE_BAR_RE = re.compile(r"^> \*\*Read this in other languages\*\*:.*$", re.MULTILINE)

def extract_headings(content: str, max_level: int = 3) -> list[tuple[int, str]]:
    """Extract H1/H2/H3 headings as (level, text) tuples."""
    pattern = re.compile(r"^(#{1," + str(max_level) + r"})\s+(.+?)\s*$", re.MULTILINE)
    return [(len(m.group(1)), m.group(2)) for m in pattern.finditer(content)]

def count_badges(content: str) -> int:
    """Count Markdown image-with-link badges (![text](badge_url))."""
    return len(re.findall(r"!\[[^\]]*\]\([^)]+\)", content))

def count_links(content: str) -> int:
    """Count Markdown links (excluding badges)."""
    all_md_links = re.findall(r"(?<!!)\[[^\]]+\]\([^)]+\)", content)
    return len(all_md_links)

def extract_language_bar(content: str) -> str | None:
    match = LANGUAGE_BAR_RE.search(content)
    return match.group(0) if match else None

def validate_pandoc(file: Path) -> bool:
    """Validate Markdown → HTML conversion per FR-604."""
    result = subprocess.run(
        ["pandoc", "-f", "gfm", "-t", "html", str(file)],
        capture_output=True, text=True
    )
    return result.returncode == 0

def check_grace_window(issue_number: int) -> bool:
    """Returns True if the GitHub issue is within the 7-day grace window."""
    result = subprocess.run(
        ["gh", "issue", "view", str(issue_number), "--json", "createdAt"],
        capture_output=True, text=True, env={**os.environ, "GH_TOKEN": os.environ["GITHUB_TOKEN"]}
    )
    if result.returncode != 0:
        return True  # No tracking issue; treat as fresh drift
    data = json.loads(result.stdout)
    created_at = datetime.fromisoformat(data["createdAt"].replace("Z", "+00:00"))
    return datetime.now(timezone.utc) - created_at < GRACE_WINDOW

def has_exempt_label(pr_number: int) -> bool:
    result = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--json", "labels"],
        capture_output=True, text=True, env={**os.environ, "GH_TOKEN": os.environ["GITHUB_TOKEN"]}
    )
    if result.returncode != 0:
        return False
    data = json.loads(result.stdout)
    return any(label["name"] == "docs-translation-exempt" for label in data["labels"])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr-number", type=int, required=False)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()

    files = [args.repo_root / f"README{loc}.md" for loc in LOCALES]
    contents = [f.read_text(encoding="utf-8") for f in files]

    canonical_headings = extract_headings(contents[0])
    canonical_badges = count_badges(contents[0])
    canonical_links = count_links(contents[0])
    canonical_lang_bar = extract_language_bar(contents[0])

    drift = []
    for f, c in zip(files[1:], contents[1:]):
        h = extract_headings(c)
        b = count_badges(c)
        l = count_links(c)
        bar = extract_language_bar(c)

        if len(h) != len(canonical_headings):
            drift.append(f"{f.name}: heading-count drift ({len(h)} vs canonical {len(canonical_headings)})")
        if b != canonical_badges:
            drift.append(f"{f.name}: badge-count drift ({b} vs canonical {canonical_badges})")
        if l != canonical_links:
            drift.append(f"{f.name}: link-count drift ({l} vs canonical {canonical_links})")
        if bar != canonical_lang_bar:
            drift.append(f"{f.name}: language-switcher-bar byte-mismatch")
        if not validate_pandoc(f):
            drift.append(f"{f.name}: pandoc rendering failure (FR-604)")

    if not drift:
        print("✓ All 6 READMEs in parity")
        sys.exit(0)

    # Drift detected
    print("⚠ Drift detected:")
    for d in drift:
        print(f"  - {d}")

    if args.pr_number and has_exempt_label(args.pr_number):
        print("ℹ docs-translation-exempt label applied — downgrading to warning")
        sys.exit(1)

    # Check grace window via tracking issue
    # (Issue-creation logic is in the GitHub Actions workflow step, NOT here)
    # If outside grace window, exit 2
    issue_number = os.environ.get("DRIFT_TRACKING_ISSUE")
    if issue_number and not check_grace_window(int(issue_number)):
        sys.exit(2)
    sys.exit(1)

if __name__ == "__main__":
    main()
```

### Track B — CI Workflow Integration

Modification to `.github/workflows/ci.yml` (sketch):

```yaml
# Add to the existing dorny/paths-filter@v3 filters at the top of ci.yml:
filters: |
  python: …                  # existing
  …                          # other existing filters
  readme:
    - 'README*.md'           # NEW

# Add a new job after the existing lint jobs:
readme-parity:
  name: README parity check
  runs-on: ubuntu-latest
  needs: [changes]
  if: needs.changes.outputs.readme == 'true'
  permissions:
    contents: read
    issues: write
    pull-requests: write
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    - name: Install pandoc
      run: sudo apt-get install -y pandoc
    - name: Run parity check
      env:
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      run: |
        python scripts/check-readme-parity.py \
          --pr-number ${{ github.event.pull_request.number }} \
          --repo-root .
    - name: Open or update tracking issue on drift
      if: failure()
      env:
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      run: |
        # Create or update the GitHub issue tracking the drift per FR-602.
        # Implementation: scripts/open-or-update-drift-issue.sh
        bash scripts/open-or-update-drift-issue.sh ${{ github.event.pull_request.number }}
```

The new weekly workflow at `.github/workflows/docs-external-links.yml`:

```yaml
name: External link check (weekly)

on:
  schedule:
    - cron: '0 6 * * 0'  # Sundays 6am UTC
  workflow_dispatch:

permissions:
  contents: read
  issues: write

jobs:
  check-external-links:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Validate external links in READMEs
        run: |
          # Use lychee or markdown-link-check (no new repo dep — installed in CI step)
          npx --yes markdown-link-check README*.md --config .github/markdown-link-check.json
      - name: Open issue on failure
        if: failure()
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh issue create \
            --title "External link rot detected in READMEs" \
            --body "Weekly link-check job failed. See workflow run: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}" \
            --label "docs,external-link-rot"
```

## Phase 2 — Implementation Order

| Phase | Goal | Tasks (T-numbers indicative; final list in tasks.md) | Wave | Parallelizable |
|---|---|---|---|---|
| **1. Setup** | Branch validation, on-disk inventory verification | T001-T003 | W13.0 | yes |
| **2. Track A — Canonical English README + diagram** | Write `README.md` + create `docs/assets/architecture-overview.svg` + draft tagline | T004-T010 | W13A | sequential |
| **3. Track B — Parity-check script** | Author `scripts/check-readme-parity.py` + tests + CI integration | T011-T020 | W13B | sequential within phase |
| **4. Track C — Translations (vendor-out-of-band)** | Commission + receive + review + commit 5 localized variants | T021-T030 | W13C | mostly parallel (5 locales) |
| **5. Finalization** | GitHub render verification + GitLab + pandoc + MkDocs + release announcement | T031-T037 | W13D | sequential |

### Wave layout

UPD-038 lands in **Wave 13** (post-UPD-037). Sub-divisions:

- **W13.0 — Setup**: T001-T003; ~0.25 dev-day; one dev.
- **W13A — Canonical English + diagram**: T004-T010; ~0.5 dev-day; one dev.
- **W13B — Parity-check script + CI**: T011-T020; ~0.5 dev-day; one dev.
- **W13C — Translations**: T021-T030; ~0.25 dev-day of internal work + 3-5 days vendor SLA wall-clock.
- **W13D — Finalization**: T031-T037; ~0.5 dev-day; one dev.

**Total internal effort: ~2 dev-days.** Wall-clock with vendor SLA: **~1 week** from kickoff.

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Translation vendor SLA miss** (5 days → 10+ days) | Medium | Medium — feature blocks W13D finalization | The brownfield input + spec assume the same vendor as feature 083 / UPD-030; if the vendor relationship is not yet established, T021's vendor-engagement step is the long-pole. T022's mitigation: ship the canonical English README + parity-check script first; localized variants land as follow-up commits (NOT a separate feature). |
| **Native-speaker reviewers unavailable for some locale** | Medium | Low — the variant ships without quality validation | Per spec assumptions: reviewer recruitment is OUT OF SCOPE; if reviewers are missing, the affected variant ships with a tracked follow-up issue. The CI parity check does NOT enforce quality. |
| **Documentation-tree links break when feature 089 / UPD-039 reorganizes** | High (will happen by definition of UPD-039) | Medium — README links 404 between UPD-038 merge and UPD-039 merge | Per plan correction §2 + R1: UPD-038 ships with valid links to today's tree; UPD-039 updates the READMEs in the SAME PR that reorganizes the docs tree. Sequencing: UPD-038 before UPD-039 is fine; same-PR updates preserve correctness. |
| **`docs/assets/architecture-overview.svg` placeholder is too plain** | Medium | Low — diagram is serviceable; feature 089 may polish | Per R2: T010 ships a 30-50-element placeholder; feature 089 can replace with a polished version as part of FR-605 reorganization. |
| **Parity-check script flaky on transient pandoc failures** | Low | Low | Pandoc is deterministic on Markdown input; flakes would indicate a bug in the script. T015's pytest tests cover the deterministic-mode behaviour. |
| **External link check (weekly) breaks on shields.io transient outages** | Medium (shields.io has occasional outages) | Low — opens a GitHub issue, NOT a CI failure | Per R5: the weekly workflow opens an issue on failure but does NOT block any PR. The issue is informational; maintainers triage and close. |
| **`gh issue create` fails due to insufficient `GITHUB_TOKEN` permissions** | Low | Medium | T015 sets `permissions: { issues: write, pull-requests: write }` in the workflow; T016 verifies via a smoke-test PR before merge. |
| **GitHub mobile app renders the language-switcher bar poorly on narrow viewports** | Medium | Low (cosmetic) | T037 verifies mobile rendering; if the bar wraps awkwardly, T037 adds CSS-friendly Markdown formatting (e.g., line breaks between locales). |
| **Chinese characters render incorrectly on GitHub** | Very Low | Low | GitHub's Markdown renderer handles UTF-8 correctly; T037 verifies the `README.zh.md` rendering inline. |
| **Existing `Makefile dev-up` target slower than 5 minutes** | Medium (first-run cold-cache) | Low | Per plan correction §10: T009's quick-start text adds a clarifying note about first-run vs. steady-state timing. |
| **License badge renders as broken image when `LICENSE` is missing** | High (LICENSE is missing per plan correction §2) | Low (cosmetic) | shields.io's `github/license` endpoint returns "no license" when missing; the badge renders as "License: not specified" — graceful degrade, NOT a broken image. T010 verifies. |

## Open Questions

These do NOT block the plan but should be tracked:

- **Q1**: Should the language-switcher bar render the current locale as a non-link "Current language" indicator OR a link that no-ops? **Working assumption**: link-with-self (e.g., `[English](./README.md)` from the English README) — simpler, every entry in the bar is a link, parity-check verifies byte-equivalence. The downside: clicking the current-language link reloads the same page — minor UX cost.
- **Q2**: Should the architecture diagram include UI screenshots (showing the platform's UI in English) OR be purely architectural (boxes-and-arrows)? **Working assumption**: purely architectural per FR-603 — UI screenshots are language-specific and would force per-locale variants of the diagram.
- **Q3**: Should the parity-check script enforce link COUNT or link CONTENT (i.e., the actual URLs)? **Working assumption**: link count + the language-switcher-bar byte-equivalence is sufficient; URL-content matching is too strict (the localized variants' "Read in English" link points to `./README.md`, not to a translated equivalent — these URLs DO differ between variants).
- **Q4**: Should the weekly external-link workflow include the localized variants? **Working assumption**: YES — the localized variants reuse the same external URLs (shields.io, GitHub Issues, Discussions); T021 includes all 6 in the link-check.
- **Q5**: Should the parity-check script run on EVERY PR (even those NOT touching READMEs) for safety? **Working assumption**: NO — the paths-filter `readme: ['README*.md']` saves CI time; PRs that don't touch READMEs cannot introduce drift.
- **Q6**: Should the 7-day grace window be configurable per repo? **Working assumption**: NO — FR-602 codifies "7 days" as the canonical window; configurable would invite drift.
- **Q7**: Should the parity-check script also verify that the localized variants' file modification times are within 7 days of the canonical English's? **Working assumption**: NO — file mtimes are unreliable across rebases / squash merges; the GitHub-issue-creation timestamp (R4) is the canonical timing source.

## Cross-Feature Coordination

| Feature | What we need from them | Owner action | Blocking? |
|---|---|---|---|
| **083 / UPD-030 (Accessibility & i18n)** | Translation vendor relationship + 7-day SLA workflow | Already established (per spec assumption) | No |
| **085 / UPD-035 (Extended E2E)** | The `make dev-up` quick-start path (delegates to `tests/e2e`) | Already on disk per Makefile inventory | No |
| **086 / UPD-036 (Admin Workbench)** | None — UPD-038 has no admin-workbench surface | n/a | No |
| **089 / UPD-039 (Documentation site reorganization)** | Updated docs-tree structure per FR-605 | UPD-039's scope; UPD-038 ships valid links to today's tree, UPD-039 updates as part of its PR | No (UPD-038 ships first) |
| **CI / GitHub Actions infrastructure** | `dorny/paths-filter@v3` action available, `GITHUB_TOKEN` with `issues: write` permission | Already on disk per `.github/workflows/ci.yml` inventory | No |

## Phase Gate

**Plan ready for `/speckit.tasks` when**:
- ✅ Constitutional anchors enumerated and gate verdicts recorded
- ✅ Brownfield-input reconciliations enumerated (12 items)
- ✅ Research decisions R1-R10 documented
- ✅ Wave placement (W13.0/A/B/C/D) confirmed
- ✅ Cross-feature coordination matrix populated
- ✅ Risk register populated with mitigations
- ✅ Open questions enumerated (none blocking)

The plan is ready. The next phase (`/speckit.tasks`) breaks the 5-phase implementation order above into ordered, dependency-annotated tasks (T001-T037, indicative).

## Complexity Tracking

> **Filled when Constitution Check has violations that must be justified.**

| Variance | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| **Documentation-tree links match TODAY's structure, not the brownfield template's structure** | Feature 089 / UPD-039 owns the FR-605 reorganization; UPD-038 cannot block on UPD-039's design | Shipping placeholder links would 404 on every visitor click — worse UX than valid-but-coarser links to the on-disk tree |
| **Architecture diagram is a placeholder, not a polished version** | Feature 089 may polish; UPD-038 ships a serviceable starter | Shipping no diagram (inline text only) violates FR-603's "diagram + 3-4 paragraphs" structure |
| **Two CI workflow integrations (ci.yml step + new docs-external-links.yml)** | Per-PR parity check + weekly external-link check have different schedules and different blocking behaviour | A single workflow handling both would mix `pull_request` and `schedule` triggers, complicating the workflow logic |
| **Python stdlib only for the parity-check script** | No new repo dependency to maintain; script is small enough that Markdown library is overkill | A `markdown` or `mistune` library would add ~50 dependencies for a 200-line script — disproportionate |
