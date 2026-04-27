# Repository Inventory for UPD-039

Verified on 2026-04-27 while implementing `089-comprehensive-documentation-site`.

## MkDocs Substrate

`mkdocs.yml` exists at the repository root and is already configured for MkDocs Material:

- `theme.name: material`
- `plugins.search` is enabled.
- 16 Material feature flags are configured:
  `navigation.tabs`, `navigation.tabs.sticky`, `navigation.sections`, `navigation.top`,
  `navigation.tracking`, `navigation.indexes`, `navigation.path`, `toc.follow`,
  `search.highlight`, `search.share`, `search.suggest`, `content.code.copy`,
  `content.code.annotate`, `content.tabs.link`, `content.tooltips`, `announce.dismiss`.

The existing navigation block references legacy paths such as
`system-architecture-v3.md`, `software-architecture-v3.md`, and
`functional-requirements-revised-v4.md`; UPD-039 replaces that nav with the FR-605
11-section structure.

## Docs Dependencies

`requirements-docs.txt` has the three baseline dependencies from the feature plan:

- `mkdocs==1.6.1`
- `mkdocs-material==9.5.45`
- `pymdown-extensions==10.12`

UPD-039 adds the MkDocs plugin dependencies in Track A.

## Existing Docs Tree

The pre-implementation `docs/` tree contains 13 Markdown files and 1 SVG asset:

- Top-level Markdown files:
  `agents.md`, `functional-requirements-revised-v6.md`,
  `software-architecture-v5.md`, `system-architecture-v5.md`
- Administration:
  `administration/audit-and-compliance.md`,
  `administration/integrations-and-credentials.md`
- Development:
  `development/structured-logging.md`
- Features:
  `features/074-security-compliance.md`,
  `features/075-model-catalog-fallback.md`,
  `features/076-privacy-compliance.md`
- Integrations:
  `integrations/webhook-verification.md`
- Operations:
  `operations/grafana-metrics-logs-traces.md`
- Asset:
  `assets/architecture-overview.svg`

The docs tree spans 7 directories when counting `docs/` itself plus
`administration/`, `assets/`, `development/`, `features/`, `integrations/`, and
`operations/`.

## Absent Root Artifacts

The repository has no `terraform/` directory at the root before UPD-039.

The repository has no root `SECURITY.md` before UPD-039. UPD-039 creates it under
the FR-618 security-disclosure task.
