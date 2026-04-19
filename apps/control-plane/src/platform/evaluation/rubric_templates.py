from __future__ import annotations

import logging
from pathlib import Path
from platform.evaluation.exceptions import TemplateLoadError
from platform.evaluation.schemas import RubricCreate

import yaml

LOGGER = logging.getLogger(__name__)


class RubricTemplateLoader:
    def __init__(self, templates_dir: Path | None = None) -> None:
        self.templates_dir = templates_dir or Path(__file__).with_name("rubrics")

    async def load_templates(self, rubric_service: object) -> int:
        count = 0
        for path in sorted(self.templates_dir.glob("*.yaml")):
            try:
                payload = yaml.safe_load(path.read_text()) or {}
            except yaml.YAMLError as exc:  # pragma: no cover - defensive
                raise TemplateLoadError(path.stem, str(exc)) from exc
            if not isinstance(payload, dict):
                raise TemplateLoadError(path.stem, "template payload must be a mapping")
            try:
                rubric = RubricCreate.model_validate(payload)
            except Exception as exc:  # pragma: no cover - defensive
                raise TemplateLoadError(path.stem, str(exc)) from exc
            upsert = getattr(rubric_service, "upsert_builtin_template", None)
            if not callable(upsert):  # pragma: no cover - defensive
                raise TemplateLoadError(
                    path.stem, "rubric service does not support template upsert"
                )
            await upsert(path.stem, rubric)
            count += 1
        LOGGER.info("Loaded %s rubric templates", count)
        return count
