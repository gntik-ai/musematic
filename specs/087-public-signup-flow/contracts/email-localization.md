# Verification Email Localization Audit

Date: 2026-04-27

## Current Path

`apps/control-plane/src/platform/accounts/email.py` delegates verification delivery to `notification_client.send_verification_email(...)` when a notification client is configured. The call passes `user_id`, `email`, `token`, and `display_name`.

When no notification client is configured, the fallback path logs that the verification email was queued. It does not render a localized template and does not receive the signup request's `Accept-Language`.

## Finding

The accounts bounded context does not currently apply `Accept-Language` to verification emails. If localized rendering exists, it is delegated to the notification client from feature 077, but the current accounts helper does not pass an explicit locale parameter.

## Scope Decision

UPD-037 should not introduce a parallel email-template system. The localization gap belongs in feature 077's notification-template roadmap: accept and persist the request locale at signup time, then pass it through `send_verification_email(...)` so the notification client can render the correct localized template.
