# Feature 083 Translation Vendor Onboarding

Date: 2026-04-29

Chosen vendor slot: Lokalise.

Repository wiring:
- English source catalogue: `apps/web/messages/en.json`
- Non-English catalogues: `apps/web/messages/{es,fr,de,ja,zh-CN}.json`
- CI sync job: `.github/workflows/ci.yml` job `localization-vendor-sync`
- Token source: `LOCALIZATION_VENDOR_API_TOKEN`, materialized for the existing SecretProvider path used by the vendor-sync job

External gate:
- Provision the Lokalise project.
- Export English source keys from `apps/web/messages/en.json`.
- Commission native-speaker review for Spanish, French, German, Japanese, and Simplified Chinese.
- Merge the first vendor-sync PR once catalogue coverage reaches the launch threshold.
