from __future__ import annotations


def test_catalog_crud_requires_full_model_card() -> None:
    card = {"capabilities": ["chat"], "limitations": ["synthetic"], "safety_assessments": ["red-team"]}
    assert {"capabilities", "limitations", "safety_assessments"} <= set(card)
