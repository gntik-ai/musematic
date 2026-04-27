# Translation Vendor Contract for UPD-038

Status: blocked pending external confirmation

## Relationship

UPD-038 is planned to reuse the same translation vendor and seven-day SLA workflow established by feature 083 / UPD-030 for UI string localization.

This workspace cannot confirm the vendor relationship or product-owner contact because that requires external coordination outside the repository.

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

Tasks T025-T032 are blocked until the vendor engagement is confirmed and translated files are received. The local implementation can still proceed for the canonical English README, parity checker, CI integration, and operator documentation.
