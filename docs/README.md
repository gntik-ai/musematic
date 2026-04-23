# musematic documentation

This directory holds the source for the public documentation site at
<https://gntik-ai.github.io/musematic/>. The site is built with
[MkDocs](https://www.mkdocs.org/) using the
[Material](https://squidfunk.github.io/mkdocs-material/) theme and is deployed
to GitHub Pages by `.github/workflows/docs.yml` on every push to `main`.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r ../requirements-docs.txt
mkdocs serve
```

Open <http://127.0.0.1:8000/> in your browser. Edits are live-reloaded.

## Build a static site

```bash
mkdocs build
# output in ../site/
```

## Deploy

Pushes to `main` trigger the `docs.yml` workflow which runs `mkdocs build` and
publishes the artifact to the `gh-pages` branch via `actions/deploy-pages`.

You do not need to run `mkdocs gh-deploy` manually — the CI workflow handles
it. To enable Pages hosting, set **Settings → Pages → Source = GitHub Actions**
in the repository settings once.

## Structure

```
docs/
├── index.md                    # Home / overview
├── getting-started.md          # Prerequisites + first run
├── installation.md             # Deployment options + env var reference
├── agents.md                   # Agent schema + 3 worked examples (end-user)
├── flows.md                    # Workflow schema + 3 worked examples (end-user)
├── features/                   # One page per implemented feature
│   └── index.md
├── administration/             # Platform-admin surface (9 pages)
│   └── index.md
├── reference/
│   └── configuration.md
├── faq.md
└── roadmap.md
```

## Contribution rules

- **No fabrication.** Every env var, config key, role name, or API path in the
  docs must be traceable to code in this repo. Unknowns become
  `TODO(andrea):` markers and a row in `../DOCS_GAPS.md`.
- **Ground every page** in a source file — spec, Pydantic model, or migration.
- **Link feature pages back** to the source spec in `specs/`.
- **One conventional commit per logical chunk** (`docs: ...` or `ci: ...`).
