# Repository Inventory for UPD-038

Inventory date: 2026-04-27

## Root files

The pre-implementation root state matched the UPD-038 correction list:

- `README.md`: absent
- `LICENSE`: absent
- `CONTRIBUTING.md`: absent
- `SECURITY.md`: absent
- `Makefile`: present
- `AGENTS.md`: present
- `CLAUDE.md`: present
- `CHANGELOG.md`: present
- `mkdocs.yml`: present

## Documentation tree

The on-disk `docs/` tree has these top-level directories:

- `docs/administration/`
- `docs/development/`
- `docs/features/`
- `docs/integrations/`
- `docs/operations/`

The on-disk `docs/` tree has these top-level Markdown files:

- `docs/agents.md`
- `docs/functional-requirements-revised-v6.md`
- `docs/software-architecture-v5.md`
- `docs/system-architecture-v5.md`

The following brownfield-template paths were absent before this implementation:

- `docs/assets/`
- `docs/getting-started.md`
- `docs/install/`
- `docs/user-guide/`
- `docs/admin-guide/`
- `docs/operator-guide/`
- `docs/developer-guide/`
- `docs/api/`
- `docs/architecture/`

## README link inputs

The canonical README documentation index must therefore link to the tree that exists today:

- Administration: `./docs/administration/`
- Operations: `./docs/operations/`
- Development: `./docs/development/`
- Features: `./docs/features/`
- Integrations: `./docs/integrations/`
- System architecture: `./docs/system-architecture-v5.md`
- Software architecture: `./docs/software-architecture-v5.md`
- Functional requirements: `./docs/functional-requirements-revised-v6.md`

`LICENSE`, `CONTRIBUTING.md`, and `SECURITY.md` are intentionally referenced as future-state informational links. UPD-038 does not create those governance files.
