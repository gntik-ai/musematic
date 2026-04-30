# Translation Vendor Contract for UPD-038

Status: local vendor workflow identified; external owner confirmation still pending

## Relationship

UPD-038 is planned to reuse the same translation vendor and seven-day SLA workflow established by feature 083 / UPD-030 for UI string localization.

Local repository evidence from `docs/localization/vendor-onboarding-083.md` identifies the feature 083 vendor workflow:

- Vendor: Lokalise
- Existing UI source catalogue: `apps/web/messages/en.json`
- Existing locale catalogues: `apps/web/messages/{es,fr,de,ja,zh-CN}.json`
- Existing CI sync job: `.github/workflows/ci.yml` job `localization-vendor-sync`
- Token source: `LOCALIZATION_VENDOR_API_TOKEN`
- Vendor project id variable: `LOKALISE_PROJECT_ID`

This workspace still cannot confirm the feature 083 owner sign-off, README-specific Lokalise project/contact, or a submitted README translation order because those require external coordination outside the repository.

## Required vendor package

When the canonical English README is approved, submit:

- `README.md`
- `specs/088-multilingual-repository-readme/contracts/canonical-english-content.md`
- The byte-identical language switcher bar
- The badge Markdown, marked do-not-translate
- All commands and file paths, marked do-not-translate
- `docs/assets/architecture-overview.svg`, marked shared and language-neutral

## Target locales

- Spanish, neutral Latin American
- Italian
- German
- French, France
- Simplified Chinese

## SLA

The target SLA is seven calendar days from vendor submission to translated README delivery.

## Current blocker

Tasks T003, T025, T026, and the native-review follow-ups remain externally gated until the README vendor engagement is confirmed with the feature 083 / UPD-030 owner. Local structural parity checks can still run against the README files currently present in the repository.
