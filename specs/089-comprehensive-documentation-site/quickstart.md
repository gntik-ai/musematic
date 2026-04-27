# Operator Documentation Quickstart

## Add a Page

1. Create the Markdown file under the correct `docs/` section.
2. Add it to `mkdocs.yml` navigation.
3. Use relative links and run `mkdocs build --strict`.
4. If the page references functional requirements, use valid `FR-NNN` IDs from `docs/functional-requirements-revised-v6.md`.

## Handle Translation Grace

English source changes under `docs/getting-started`, `docs/user-guide`, and `docs/admin-guide` start a seven-day localization grace window. Submit those source pages to the vendor, place returned files using suffixes such as `.es.md`, and run `scripts/check-doc-translation-parity.py`.

## Regenerate References

```bash
python scripts/generate-env-docs.py --output docs/configuration/environment-variables.md
helm-docs --chart-search-root=deploy/helm
python scripts/aggregate-helm-docs.py --output docs/configuration/helm-values.md
python scripts/export-openapi.py
python scripts/check-doc-references.py docs
```

## Redeploy

The docs workflow deploys from `main` with:

```bash
mike deploy --push --update-aliases v1.3.0 latest
```

For pull requests, inspect the uploaded `site/` artifact before merge.
