# UPD-042 Constitution Confirmation

Date: 2026-04-27
Source: `.specify/memory/constitution.md`

## Confirmed Anchors

- Rule 9, lines 118-122: PII operations must emit audit-chain entries and use the audit-chain service rather than direct writes.
- Rule 30, lines 198-202: admin endpoints require `require_admin` or `require_superadmin`. UPD-042 `/me/*` endpoints are user-self endpoints, so this admin-only gate is not applicable.
- Rule 31, lines 203-207: super-admin bootstrap secrets must not be logged. UPD-042 also remains subject to broader secret-handling rules 23, 39, 40, and 44 when rendering one-time API keys or MFA material.
- Rule 34, lines 217-221: impersonation must double-audit both the acting admin and effective user.
- Rule 45, lines 258-262: every user-facing backend capability requires a UI surface.
- Rule 46, lines 263-267: `/api/v1/me/*` endpoints accept no `user_id` parameter and operate on the authenticated principal.

## Spec Amendment Note

The UPD-042 plan and task list refer to "Rule 41 — Accessibility AA". In the current constitution, Rule 41 is "Vault failure does not bypass authentication" at lines 244-248. The active accessibility rule is Rule 28 at lines 190-192: "Accessibility is tested, not promised."

Implementation should treat the accessibility requirement as constitution Rule 28, not Rule 41. This is a numbering correction only; the AA testing obligation remains in force.
