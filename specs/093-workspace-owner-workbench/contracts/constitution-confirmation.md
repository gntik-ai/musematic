# UPD-043 Constitution Confirmation

Date: 2026-04-27
Source: `.specify/memory/constitution.md`

## Confirmed Anchors

- Rule 9, lines 118-122: PII operations must emit audit-chain entries and use the audit-chain service rather than direct writes.
- Rule 10, lines 123-126: credentials must go through vault and rotation-capable credentials use the secret rotation service.
- Rule 30, lines 198-202: admin endpoints require an explicit admin or super-admin gate.
- Rule 33, lines 213-216: 2PA must be enforced server-side; clients may display the requirement but servers validate the token freshly on apply.
- Rule 45, lines 258-262: every user-facing backend capability requires a user-facing UI surface.
- Rule 47, lines 268-273: workspace-scoped resources must be visually distinguished from platform-scoped resources and enforced by the backend.

## Numbering Correction

The UPD-043 plan and tasks refer to "Rule 41 — Accessibility AA". In the current constitution, Rule 41 is "Vault failure does not bypass authentication" at lines 244-248. The active accessibility rule is Rule 28 at lines 190-192: "Accessibility is tested, not promised."

Implementation should treat the accessibility requirement as constitution Rule 28, not Rule 41. This is a numbering correction only; the AA testing obligation remains in force.
