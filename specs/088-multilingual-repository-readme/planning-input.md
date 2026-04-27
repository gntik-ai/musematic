# Planning Input — UPD-038 Multilingual Repository README

> **Captured verbatim from the user's `/speckit.specify` invocation on 2026-04-27.** This file is the immutable record of the brownfield context that authored spec.md. Edits MUST NOT be made here; if a correction is needed, edit spec.md and append a note to the corrections list at the top of this file.

## Corrections Applied During Spec Authoring

1. **6 README variants total**, not "5 localized" alone. Brownfield writes "five localized variants"; FR-600 enumerates 6 file names total (English canonical + 5 localized). Spec adopts 6.
2. **Missing root files referenced by READMEs.** No README.md, LICENSE, CONTRIBUTING.md, or SECURITY.md at the repo root today (verified). Spec scopes UPD-038 to the 6 README files + parity-check script; LICENSE / CONTRIBUTING / SECURITY are OUT OF SCOPE.
3. **Documentation index links.** On-disk `docs/` tree has different subdirectories than the brownfield template's `./docs/user-guide/` etc. Spec uses the on-disk tree TODAY; feature 089 / UPD-039 reorganizes per FR-605.
4. **Architecture diagram path.** `./docs/assets/architecture-overview.svg` does NOT exist on disk. Plan-phase decision: create placeholder OR reference existing OR use inline text fallback.
5. **`make dev-up` quick-start verified** at `Makefile:38`.
6. **GitHub repo URL `gntik-ai/musematic`** verified via PR merge commits.
7. **Language switcher byte-equivalence**: the bar's MARKDOWN is byte-identical across all 6 variants; only surrounding prose differs.
8. **7-day translation grace window** codified in FR-602; tracked as auto-created GitHub issue.

---

# UPD-038 — Multilingual Repository README

## Brownfield Context

**Current state (verified in repo):**
- No `README.md` at the repository root.
- `docs/` folder contains only technical specs (FR, system architecture, software architecture v4).
- No user-facing introduction to the project.
- No badges, no quick start, no visible project homepage.

**FRs:** FR-600 through FR-604 (section 111).

---

## Summary

UPD-038 delivers a canonical English `README.md` and five localized variants (Spanish, Italian, German, French, Simplified Chinese). Each README is a self-contained introduction covering tagline, description, capabilities, quick start, installation overview, architecture snapshot, documentation index, contributing pointers, license, and community links. A CI check enforces translation parity. Translations are treated as production artifacts, not afterthoughts.

---

## User Scenarios

### User Story 1 — First-time visitor (Priority: P1)

A developer lands on the GitHub repo having heard of Musematic but knowing nothing about it. They want to decide in 60 seconds whether to keep reading.

**Independent Test:** Read the English README top-to-bottom in 2 minutes. Decide whether to explore the repo further.

**Acceptance:**
1. Top section clearly states what Musematic is and for whom.
2. Quick-start command visible in the first viewport.
3. Links to detailed guides visible without scrolling deep.
4. Architecture diagram summarizes the system at a glance.
5. Badges show build status, license, version, supported Kubernetes versions.

### User Story 2 — Spanish-speaking evaluator (Priority: P1)

A Spanish-speaking product manager wants to evaluate the platform in their native language before involving engineering.

**Independent Test:** Click the "Español" link at the top of the English README, read the Spanish README. Compare quality and completeness to English.

**Acceptance:**
1. Language switcher at the top of each README.
2. Spanish README has all sections present in the English README.
3. Translations are idiomatic (native reviewer reports quality).
4. Links work (no broken links to missing localized docs).
5. Code blocks and command examples remain in English (as commands are English).

### User Story 3 — Translation drift detection (Priority: P2)

A contributor adds a new section to the English README without updating translations.

**Independent Test:** Submit a PR touching only `README.md`. CI check runs. Contributor sees a clear warning linking to the drift.

**Acceptance:**
1. CI check compares section headings across all six READMEs.
2. CI check validates link integrity within all READMEs.
3. When drift is detected, CI emits a friendly warning (not a hard fail within the 7-day grace period).
4. After 7 days, drift becomes a hard fail.
5. Grace period is trackable via a GitHub issue auto-created by the CI check.

---

### Edge Cases

- **New README section added in English**: CI warns until translations catch up within 7 days; after 7 days it fails the build.
- **Translation corrections (typo fixes)**: do not require updates to other language READMEs.
- **Link rot to external resources**: CI check validates external links weekly (not on every PR, to avoid flaky failures).
- **Localized UI screenshots**: allowed per-variant but not required; architecture diagrams stay in English and are shared.

---

## README Structure

Each README contains these sections, in this order:

```markdown
# Musematic — Agentic Mesh Platform

[![Build](https://img.shields.io/github/actions/workflow/status/gntik-ai/musematic/ci.yml)]()
[![License](https://img.shields.io/github/license/gntik-ai/musematic)]()
[![Kubernetes](https://img.shields.io/badge/kubernetes-1.28%2B-blue)]()
[![Version](https://img.shields.io/github/v/release/gntik-ai/musematic)]()

> **Read this in other languages**: [English](./README.md) · [Español](./README.es.md) · [Italiano](./README.it.md) · [Deutsch](./README.de.md) · [Français](./README.fr.md) · [简体中文](./README.zh.md)

**One-paragraph tagline describing Musematic.**

---

## What is Musematic?

Accessible description of the platform's purpose, target users, and differentiators.

## Core capabilities

- **Agent Lifecycle Management** — registration, certification, revision, decommissioning
- **Multi-Agent Orchestration** — workspaces, goals, fleets, governance
- **Trust and Compliance** — policies, observers, judges, enforcers, audit trail, GDPR, SOC2 evidence
- **Reasoning** — Chain of Thought, Tree of Thought, ReAct, Chain of Debates, Scaling Inference
- **Evaluation** — trajectory scoring, LLM-as-Judge, semantic testing, fairness metrics
- **Observability** — Prometheus, Grafana, Jaeger, Loki with 21 built-in dashboards
- **Cost Governance** — per-execution attribution, budgets with hard caps, chargeback, anomaly detection
- **Portability** — runs on kind, k3s, managed Kubernetes, or bare metal with Hetzner Cloud

## Quick start

Five minutes to a running local install:

```bash
git clone https://github.com/gntik-ai/musematic.git
cd musematic
make dev-up    # Creates kind cluster, installs Helm charts, seeds test data
open http://localhost:8080    # Default admin credentials printed in terminal
```

See the [Getting Started Guide](./docs/getting-started.md) for a walkthrough.

## Installation options

| Target | Use case | Guide |
|---|---|---|
| kind | Local development, CI E2E | [Install on kind](./docs/install/kind.md) |
| k3s | Single-node lab or small production | [Install on k3s](./docs/install/k3s.md) |
| Hetzner + LB | Production with managed load balancer | [Install on Hetzner](./docs/install/hetzner.md) |
| GKE / EKS / AKS | Managed cloud Kubernetes | [Install on managed K8s](./docs/install/managed.md) |

## Architecture at a glance

![Architecture diagram](./docs/assets/architecture-overview.svg)

Musematic is a control-plane + satellite-services architecture running on Kubernetes. The Python control plane manages lifecycle, governance, and orchestration; Go satellite services handle runtime, sandboxing, reasoning, and simulation. Event bus via Kafka. State in PostgreSQL + Redis + Qdrant + Neo4j + ClickHouse + OpenSearch + S3. Observability via Prometheus + Grafana + Jaeger + Loki.

## Documentation

- [User Guide](./docs/user-guide/)
- [Administrator Guide](./docs/admin-guide/)
- [Operator Guide](./docs/operator-guide/)
- [Developer Guide](./docs/developer-guide/)
- [API Reference](./docs/api/)
- [Architecture](./docs/architecture/)

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for how to report issues, propose changes, and submit pull requests.

## License

See [LICENSE](./LICENSE).

## Community and support

- Issues: [GitHub Issues](https://github.com/gntik-ai/musematic/issues)
- Discussions: [GitHub Discussions](https://github.com/gntik-ai/musematic/discussions)
- Security disclosure: see [SECURITY.md](./SECURITY.md) — email `security@musematic.ai`
```

The six variants keep structure and links identical; prose is translated by the translation vendor (same workflow as UPD-030 for the UI).

## Translation Management

- Source of truth: English `README.md`.
- Translation workflow: every PR that touches `README.md` triggers a translation job assigned to the vendor with a 7-day SLA.
- CI check: `scripts/check-readme-parity.py` compares section headings (H1 through H3), badges, and link count across all six variants. Outputs a diff if anything is missing.
- During the 7-day grace window: CI posts a warning (non-blocking) with the diff.
- After 7 days: CI fails the build unless an exception label (`docs-translation-exempt`) is applied by a maintainer.
- Emergency (security issue requiring immediate disclosure in English): maintainer applies exemption; follow-up translation tracked as issue with 30-day hard SLA.

## Acceptance Criteria

- [ ] `README.md` exists at repo root with all 11 sections
- [ ] `README.es.md`, `README.it.md`, `README.de.md`, `README.fr.md`, `README.zh.md` exist with parity
- [ ] Language switcher bar at top of each variant
- [ ] Badges render correctly on GitHub
- [ ] Architecture diagram (SVG) reachable and accessible
- [ ] CI check `scripts/check-readme-parity.py` runs on every PR
- [ ] CI warnings / failures documented with remediation steps
- [ ] Native-speaker reviewer confirms quality of each non-English translation
- [ ] Links in every variant are valid (external link check runs weekly)
