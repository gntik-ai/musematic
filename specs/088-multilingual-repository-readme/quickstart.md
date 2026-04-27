# Operator README Workflow

This walkthrough is the contributor-facing companion to FR-602. It explains how to change the canonical English README without letting translated variants drift silently.

## Add or change canonical English content

1. Edit `README.md`.
2. Keep the language switcher byte-identical:

```markdown
> **Read this in other languages**: [English](./README.md) · [Español](./README.es.md) · [Italiano](./README.it.md) · [Deutsch](./README.de.md) · [Français](./README.fr.md) · [简体中文](./README.zh.md)
```

3. Do not translate commands, paths, badge URLs, or architecture diagram paths.
4. If adding a new H1/H2/H3 heading, expect the parity checker to require the same heading structure in every localized README.

## Submit translation work

Send the vendor package described in `contracts/translation-vendor.md`:

- `README.md`
- `contracts/canonical-english-content.md`
- The exact language switcher bar
- Badge Markdown marked do-not-translate
- Command and path blocks marked do-not-translate
- `docs/assets/architecture-overview.svg` marked shared and language-neutral

The intended SLA is seven calendar days.

## Run the local parity check

```bash
python scripts/check-readme-parity.py --repo-root .
```

Exit codes:

- `0`: all variants are structurally aligned.
- `1`: drift exists, but it is still a warning.
- `2`: hard failure, such as missing README variants, pandoc rendering failure, or drift past the seven-day grace window.

## Handle the CI drift issue

When a PR touches `README*.md`, `.github/workflows/ci.yml` runs the parity check.

If drift is found, the workflow:

- posts the parity output as a PR comment,
- opens or updates a `README translation drift: PR #{N}` issue,
- starts the seven-day grace window from the tracking issue creation time,
- fails only when the script exits with code `2`.

## Emergency disclosures

For urgent English-only changes, a maintainer may apply `docs-translation-exempt` to the PR.

The helper script then creates or updates:

```text
README translation backfill (30-day SLA): PR #{N}
```

The exemption keeps the parity check as a warning, but it does not remove the translation obligation.

Repository label setup, if needed:

```bash
gh label create docs-translation-exempt \
  --color d73a4a \
  --description "Exempts the PR from the README parity check; requires 30-day backfill follow-up issue per FR-602"
```
