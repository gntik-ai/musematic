from __future__ import annotations

from dataclasses import dataclass, field
from platform.common.exceptions import ValidationError
from platform.common.tagging.constants import LABEL_KEY_PATTERN, TAG_PATTERN

from fastapi import Request


@dataclass(frozen=True, slots=True)
class TagLabelFilterParams:
    tags: list[str] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)


def parse_tag_label_filters(request: Request) -> TagLabelFilterParams:
    tags: list[str] = []
    labels: dict[str, str] = {}

    raw_tags = request.query_params.get("tags")
    if raw_tags:
        for item in raw_tags.split(","):
            tag = item.strip()
            if not tag:
                continue
            if not TAG_PATTERN.fullmatch(tag):
                raise ValidationError(
                    "INVALID_TAG_FILTER",
                    "Tag filters must match ^[a-zA-Z0-9._-]+$.",
                    {"tag": tag},
                )
            tags.append(tag)

    for key, value in request.query_params.multi_items():
        if not key.startswith("label."):
            continue
        label_key = key.removeprefix("label.").strip()
        if not label_key or not LABEL_KEY_PATTERN.fullmatch(label_key):
            raise ValidationError(
                "INVALID_LABEL_FILTER",
                "Label filter parameters must be formatted as label.<key>=<value>.",
                {"parameter": key},
            )
        labels[label_key] = value.strip()

    return TagLabelFilterParams(tags=tags, labels=labels)

