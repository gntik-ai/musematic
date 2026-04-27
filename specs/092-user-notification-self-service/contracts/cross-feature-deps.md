# UPD-042 Cross-Feature Dependency Check

Date: 2026-04-27

## Confirmed Dependencies

- UPD-036 Administrator Workbench is merged to `main`: `b77e4af Merge pull request #85 from gntik-ai/086-administrator-workbench-and`.
- UPD-037 Public Signup is merged to `main`: `e4d281f Merge pull request #86 from gntik-ai/087-public-signup-flow`.
- UPD-039 Comprehensive Documentation is merged to `main`: `d70b644 Merge pull request #89 from gntik-ai/089-comprehensive-documentation-site`.
- UPD-077 Multi-Channel Notifications is merged to `main`: `0d172c9 Merge pull request #76 from gntik-ai/077-multi-channel-notifications`.

## On-Disk Verification

- Admin settings UI exists under `apps/web/components/features/admin/` and `apps/web/app/(main)/admin/settings/page.tsx`.
- Public signup UI exists under `apps/web/app/(auth)/signup/`.
- Consent capture helpers and tests exist in `tests/e2e/journeys/test_helpers_contract.py`.
- Notification channels include `DeliveryMethod` values `in_app`, `email`, `webhook`, `slack`, `teams`, and `sms`.
- Deliverer modules exist for email, webhook, Slack, Teams, and SMS under `apps/control-plane/src/platform/notifications/deliverers/`; in-app delivery is implemented through the persistent `UserAlert` model and publish path.
- Documentation directories from UPD-039 exist, including `docs/operator-guide/runbooks/`, `docs/admin-guide/`, `docs/developer-guide/`, and `docs/release-notes/`.

## Documentation Placement

Because UPD-039 has landed, UPD-042 runbooks and guides should be added under:

- `docs/operator-guide/runbooks/`
- `docs/admin-guide/`
- `docs/developer-guide/`
- `docs/release-notes/`
