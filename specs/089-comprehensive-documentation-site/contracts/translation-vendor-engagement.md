# Translation Vendor Engagement for UPD-039

UPD-039 reuses the localization vendor relationship established by the
localization bounded context and the multilingual README work.

## Vendor

The active on-disk platform setting is `LOCALIZATION_TRANSLATION_VENDOR`, with the
default value `lokalise` in
`apps/control-plane/src/platform/common/config.py`.

The implementation therefore records Lokalise as the expected vendor for docs
translation coordination until a procurement owner replaces that setting with a
different production vendor.

## Scope

The official FR-620 docs locale set is:

- English (`en`) as the canonical source
- Spanish (`es`)
- German (`de`)
- French (`fr`)
- Italian (`it`)
- Simplified Chinese (`zh-CN`)

Localized sections are limited to:

- `getting-started/`
- `user-guide/`
- `admin-guide/`

Technical sections remain English-only: Operator Guide, Developer Guide, API
Reference, Architecture, Installation, Configuration, Security, and Release Notes.

The expected delivery package is 50+ canonical English pages translated into 5
non-English locales, or approximately 250 localized Markdown files once the source
pages are complete.

## SLA and Review Gate

The FR-602 / feature 088 drift policy applies: source changes are expected to be
translated within 7 days or tracked with a drift issue.

Native-speaker review remains an external gate. A localized page is not considered
final until the reviewer records a quality score of at least 4/5 and confirms that
page-context language switching preserves the current page.

## UPD-039 Submission Status

As of 2026-04-27, the canonical English source pages have been prepared locally but
have not been submitted to the vendor from this workspace. Submission requires the
project owner's vendor credentials and should include the `getting-started/`,
`user-guide/`, and `admin-guide/` trees only.
