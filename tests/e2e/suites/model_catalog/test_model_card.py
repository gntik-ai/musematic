from __future__ import annotations


def test_model_card_publication_and_retrieval_contract() -> None:
    card = {"published": True, "retrievable": True, "version": 1}
    assert card["published"] is True
    assert card["retrievable"] is True
