# UPD-042 Repository Inventory

Date: 2026-04-27
Branch: `092-user-notification-self-service`

## Upstream Wave Status

- UPD-040 is merged to `main`: `e5374bb Merge pull request #90 from gntik-ai/090-hashicorp-vault-integration`.
- UPD-041 is merged to `main`: `2cf5cdb Merge pull request #91 from gntik-ai/091-oauth-env-bootstrap`.
- Implementation is not blocked by the UPD-040/UPD-041 merge gate.

## Required File Inventory

- `apps/control-plane/src/platform/common/secret_provider.py`: present.
- `apps/web/components/features/alerts/notification-bell.tsx`: present and fully implemented. `wc -l` reports 151 lines; the component uses `useAlertFeed`, `/me/alerts?limit=20`, `/me/alerts/unread-count`, a dropdown, and unread badge state.
- `apps/control-plane/src/platform/notifications/router.py`: existing `/me` notifications router present. Lines 28-84 expose:
  - `GET /me/alert-settings`
  - `PUT /me/alert-settings`
  - `GET /me/alerts`
  - `GET /me/alerts/unread-count`
  - `PATCH /me/alerts/{alert_id}/read`
  - `GET /me/alerts/{alert_id}`
- `apps/control-plane/src/platform/auth/router.py`: `POST /logout` and `POST /logout-all` are present in the auth router.
- `apps/control-plane/src/platform/auth/session.py`: `delete_session` and `delete_all_sessions` exist. `list_sessions_by_user` does not exist yet and remains a UPD-042 implementation task.
- `apps/control-plane/migrations/versions/069_oauth_provider_env_bootstrap.py`: present. Highest migration sequence is `069`, so UPD-042 uses `070_user_self_service_extensions.py`.

## Notes

- The existing notifications URL convention is `/me/alerts*`; UPD-042 should preserve it and add only `POST /me/alerts/mark-all-read` to the notifications router.
- The existing notification bell is not a placeholder. UPD-042 should reduce its dropdown query from 20 to 5 and add the `/notifications` see-all path.
