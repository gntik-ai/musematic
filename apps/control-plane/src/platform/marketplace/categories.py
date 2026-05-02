"""Marketing-category enumeration for public-marketplace agents.

Used when an agent owner submits a public-scope publication request per
UPD-049 (FR-007). The category appears on the marketplace listing card and
in the `/admin/marketplace-review` queue.

The enumeration is platform-curated (research R4 — UPD-049). Revising the
list does NOT require a database migration — the Pydantic schema in
`registry/schemas.py:MarketingMetadata` validates against this constant
at request time.

Mirror: the frontend constants module at
`apps/web/lib/marketplace/categories.ts` MUST be kept in sync (UPD-049
T038). A CI parity check enforces equality.
"""

from __future__ import annotations

MARKETING_CATEGORIES: tuple[str, ...] = (
    "data-extraction",
    "summarisation",
    "code-assistance",
    "research",
    "automation",
    "communication",
    "analytics",
    "content-generation",
    "translation",
    "other",
)
"""The platform-curated category list. Used by the publish-with-public-scope
flow (FR-007). The string `other` is the catch-all and is intentionally last
so the dropdown ordering reads from most-specific to most-generic."""
