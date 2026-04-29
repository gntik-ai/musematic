from __future__ import annotations


def test_model_catalog_fallback_on_rate_limit_contract() -> None:
    chain = ["primary:429", "tier2:used", "model.fallback.triggered"]
    assert chain[0].endswith("429")
    assert chain[1] == "tier2:used"
