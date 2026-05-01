"""Reserved tenant slugs required by SaaS-9 and FR-003 defense in depth."""

RESERVED_SLUGS: frozenset[str] = frozenset(
    {
        "api",
        "grafana",
        "status",
        "www",
        "admin",
        "platform",
        "webhooks",
        "public",
        "docs",
        "help",
    }
)
