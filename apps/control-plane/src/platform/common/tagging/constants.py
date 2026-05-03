from __future__ import annotations

import re

ENTITY_TYPES = (
    "workspace",
    "agent",
    "fleet",
    "workflow",
    "policy",
    "certification",
    "evaluation_run",
    # UPD-051 (spec 104) — data_lifecycle entity types.
    "data_export_job",
    "deletion_job",
    "sub_processor",
)

RESERVED_LABEL_PREFIXES = ("system.", "platform.")

MAX_TAGS_PER_ENTITY = 50
MAX_LABELS_PER_ENTITY = 50
MAX_TAG_LEN = 128
MAX_LABEL_KEY_LEN = 128
MAX_LABEL_VALUE_LEN = 512

TAG_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")
LABEL_KEY_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9._-]*$")

REDIS_KEY_AST_TEMPLATE = "tags:label_expression_ast:{policy_id}:{version}"
REDIS_KEY_AST_TTL_SECONDS = 86_400

