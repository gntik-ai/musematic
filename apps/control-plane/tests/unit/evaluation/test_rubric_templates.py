from __future__ import annotations

from pathlib import Path
from platform.evaluation.exceptions import TemplateLoadError
from platform.evaluation.rubric_templates import RubricTemplateLoader
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_rubric_template_loader_upserts_yaml_templates(tmp_path: Path) -> None:
    (tmp_path / "correctness.yaml").write_text(
        """
name: correctness
description: Checks factual accuracy
criteria:
  - name: factual_accuracy
    description: Is it right?
    scale: 5
""".lstrip()
    )
    (tmp_path / "style.yaml").write_text(
        """
name: style
description: Checks style
criteria:
  - name: clarity
    description: Is it clear?
    scale: 5
""".lstrip()
    )
    rubric_service = type(
        "RubricServiceStub",
        (),
        {"upsert_builtin_template": AsyncMock()},
    )()

    count = await RubricTemplateLoader(tmp_path).load_templates(rubric_service)

    assert count == 2
    assert rubric_service.upsert_builtin_template.await_count == 2
    names = [call.args[0] for call in rubric_service.upsert_builtin_template.await_args_list]
    assert names == ["correctness", "style"]


@pytest.mark.asyncio
async def test_rubric_template_loader_rejects_invalid_payloads(tmp_path: Path) -> None:
    (tmp_path / "invalid.yaml").write_text("[]\n")

    with pytest.raises(TemplateLoadError):
        await RubricTemplateLoader(tmp_path).load_templates(object())
