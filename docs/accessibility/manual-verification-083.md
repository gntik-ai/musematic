# Feature 083 Manual Accessibility Verification

Date: 2026-04-29

Scope:
- VoiceOver on macOS and NVDA on Windows across audited surfaces.
- High-Contrast theme and localized ARIA labels.
- Keyboard-only route traversal and modal dismissal quality.

Current status:
- Automated axe-core wiring is committed under `apps/web/tests/a11y/`.
- Manual assistive-technology execution remains an external pre-merge gate because this workspace does not provide VoiceOver/NVDA runtime access.

Checklist for the external pass:
- Navigate login, marketplace, agent detail, workflow editor, operator dashboard, settings preferences, and admin locales with keyboard only.
- Verify `?` opens the shortcut help overlay only outside editable controls.
- Verify status badges announce textual severity, not color alone.
- Verify High-Contrast focus outlines are visible on all controls.
- Verify Spanish locale announces platform labels in Spanish while user-generated content remains unchanged.
