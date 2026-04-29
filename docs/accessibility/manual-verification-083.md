# Feature 083 Manual Accessibility Verification

Date: 2026-04-29

Scope:

- VoiceOver on macOS and NVDA on Windows across audited surfaces.
- High-Contrast theme and localized ARIA labels.
- Keyboard-only route traversal and modal dismissal quality.

Current status:

- Automated axe-core wiring is committed under `apps/web/tests/a11y/`.
- Manual assistive-technology execution remains an external pre-merge gate
  because this Linux workspace does not provide VoiceOver or NVDA runtime access.

Audited surfaces:

- Login
- Marketplace listing
- Agent detail
- Workflow editor / monitor
- Operator dashboard
- Settings preferences
- Admin locales

Checklist for the external pass:

- Navigate each audited surface with keyboard only.
- Verify `?` opens the shortcut help overlay only outside editable controls.
- Verify Escape closes dialogs, popovers, command palette, and help overlay.
- Verify status badges announce textual severity, not color alone.
- Verify High-Contrast focus outlines are visible on all controls.
- Verify Spanish locale announces platform labels in Spanish while
  user-generated content remains unchanged.
- Verify text resized to 200 percent does not hide critical actions.

Result log:

| Date | Runtime | Tester | Result | Notes |
|------|---------|--------|--------|-------|
| 2026-04-29 | Linux automation only | Codex | Blocked | axe-core artifacts exist; VoiceOver/NVDA pass requires external macOS/Windows runtime. |
