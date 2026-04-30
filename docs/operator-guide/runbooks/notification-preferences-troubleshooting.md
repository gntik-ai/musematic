# Notification Preferences Troubleshooting

Use this runbook when a user reports missing, delayed, duplicated, or unexpected notifications from the FR-649 notification inbox or FR-651 preferences matrix.

## Symptom

- The user does not receive in-app, email, webhook, Slack, Teams, or SMS notifications.
- The `/notifications` page shows alerts but the expected external channel did not deliver.
- Quiet hours or digest mode delayed a non-critical alert.
- A mandatory `security.*` or `incidents.*` event appears enabled even after the user tried to disable it.

## Diagnosis

1. Confirm the alert exists in the persistent inbox with `GET /api/v1/me/alerts` while impersonating only through an approved support path.
2. Check the user's extended notification preferences:
   - `per_channel_preferences` maps event types to enabled channels.
   - `digest_mode` maps each channel to `immediate`, `hourly`, or `daily`.
   - `quiet_hours` stores `start_time`, `end_time`, and `timezone`.
3. For `security.*` and `incidents.*`, confirm at least one channel remains enabled. These events are mandatory by design.
4. Check channel-specific delivery ledgers and provider health for webhook, Slack, Teams, SMS, and email delivery failures.

## Remediation

1. Ask the user to review `/settings/notifications` and save the event-channel matrix.
2. For quiet-hours issues, confirm the timezone is correct and explain that critical events bypass quiet hours.
3. For digest mode, switch the affected channel to `immediate` when operational urgency matters.
4. For provider delivery failures, rotate or re-verify the affected channel credential using the relevant integration runbook.

## Verification

- Trigger `POST /api/v1/me/notification-preferences/test/{event_type}` for a non-sensitive test event.
- Confirm the test alert appears in `/notifications`.
- Confirm the selected channel receives the delivery or records a clear provider error.
- Confirm `notifications.preferences.updated` exists in the user's audit trail after preference changes.
