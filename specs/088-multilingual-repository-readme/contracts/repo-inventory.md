# Repository Inventory for UPD-038

Inventory date: 2026-04-30

## Root files

The pre-implementation root state matched the UPD-038 correction list. A later
documentation-site update added `SECURITY.md`, but `LICENSE` and
`CONTRIBUTING.md` are still absent and remain outside UPD-038.

- `README.md`: absent
- `LICENSE`: absent
- `CONTRIBUTING.md`: absent
- `SECURITY.md`: present
- `Makefile`: present
- `AGENTS.md`: present
- `CLAUDE.md`: present
- `CHANGELOG.md`: present
- `mkdocs.yml`: present

## Documentation tree

The current on-disk `docs/` tree has these top-level directories:

- `docs/accessibility/`
- `docs/admin-guide/`
- `docs/api-reference/`
- `docs/architecture/`
- `docs/assets/`
- `docs/configuration/`
- `docs/developer-guide/`
- `docs/getting-started/`
- `docs/installation/`
- `docs/localization/`
- `docs/operator-guide/`
- `docs/reference/`
- `docs/release-notes/`
- `docs/security/`
- `docs/user-guide/`

The on-disk `docs/` tree has these top-level Markdown files:

- `docs/functional-requirements-revised-v6.md`
- `docs/functional-requirements-saas-pass.md`
- `docs/index.md`
- `docs/software-architecture-v6.md`
- `docs/system-architecture-v6.md`

The following brownfield-template paths were absent before the UPD-038
implementation but now exist through documentation-site follow-up work:

- `docs/user-guide/`
- `docs/admin-guide/`
- `docs/operator-guide/`
- `docs/developer-guide/`
- `docs/architecture/`

## README link inputs

The README documentation index now links to the tree that exists today:

- Administration: `./docs/admin-guide/`
- Operations: `./docs/operator-guide/`
- Development: `./docs/developer-guide/`
- User guide: `./docs/user-guide/`
- Integrations: `./docs/admin-guide/integrations.md`
- Agent builder guide: `./docs/developer-guide/building-agents.md`
- System architecture: `./docs/system-architecture-v6.md`
- Software architecture: `./docs/software-architecture-v6.md`
- Functional requirements: `./docs/functional-requirements-revised-v6.md`

`LICENSE` and `CONTRIBUTING.md` are intentionally referenced as future-state
informational links. UPD-038 does not create those governance files.
