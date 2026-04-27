# UPD-044 Cross-Feature Dependencies

Date: 2026-04-28

Observed dependencies in the working tree:

- Agent contracts backend is present in `platform.trust`.
- Notification and alert surfaces are present in `platform.notifications` and `components/features/alerts`.
- Zero-trust visibility support is present in policy/governance and registry visibility fields.
- Multi-channel notifications are present in the `058_multi_channel_notifications.py` migration and notification integration tests.
- Documentation directories exist; UPD-044 docs can land under `docs/operator-guide/runbooks/` and `docs/developer-guide/`.

UPD-044 implementation proceeds with additive backend changes and does not block on missing dependency code in the local tree.

