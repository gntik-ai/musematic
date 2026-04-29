# Feature 083 Translation Vendor Onboarding

Date: 2026-04-29

Chosen vendor: Lokalise.

Repository wiring:

- English source catalogue: `apps/web/messages/en.json`
- Non-English catalogues: `apps/web/messages/{es,fr,de,ja,zh-CN}.json`
- CI sync job: `.github/workflows/ci.yml` job `localization-vendor-sync`
- Sync implementation: `apps/control-plane/src/platform/localization/tooling/vendor_sync.py`
- Token source: `LOCALIZATION_VENDOR_API_TOKEN`, materialized for the existing
  SecretProvider path used by the vendor-sync job
- Vendor project id: `LOKALISE_PROJECT_ID`

External gate:

- Provision the Lokalise project.
- Import the English source keys from `apps/web/messages/en.json`.
- Configure file exports as JSON catalogues named `{locale}.json`.
- Commission native-speaker review for Spanish, French, German, Japanese, and
  Simplified Chinese.
- Run the first vendor-sync job and merge the generated PR once catalogue
  coverage reaches the launch threshold.

Acceptance evidence required before T083 can be checked off:

- Lokalise project URL and project id recorded in the release checklist.
- Confirmation that every key in `apps/web/messages/en.json` exists in each
  non-English catalogue or has an approved grace-window exception.
- Native-review approval for `es`, `fr`, `de`, `ja`, and `zh-CN`.
- A merged `chore: sync localization catalogues` PR produced by the CI sync job.
