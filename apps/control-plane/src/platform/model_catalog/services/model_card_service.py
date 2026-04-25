from __future__ import annotations

from platform.common.events.producer import EventProducer
from platform.common.exceptions import NotFoundError
from platform.model_catalog.events import (
    ModelCardPublishedPayload,
    publish_model_card_published,
)
from platform.model_catalog.models import ModelCard
from platform.model_catalog.repository import ModelCatalogRepository
from platform.model_catalog.schemas import ModelCardFields, ModelCardResponse
from typing import Any
from uuid import UUID, uuid4


class ModelCardService:
    def __init__(
        self,
        repository: ModelCatalogRepository,
        *,
        producer: EventProducer | None = None,
        trust_service: Any | None = None,
    ) -> None:
        self.repository = repository
        self.producer = producer
        self.trust_service = trust_service

    async def upsert_card(
        self,
        catalog_entry_id: UUID,
        request: ModelCardFields,
    ) -> ModelCardResponse:
        entry = await self.repository.get_entry(catalog_entry_id)
        if entry is None:
            raise NotFoundError("MODEL_CATALOG_ENTRY_NOT_FOUND", "Catalogue entry not found")
        existing = await self.repository.get_card_by_entry_id(catalog_entry_id)
        material = False
        if existing is None:
            card = await self.repository.add(
                ModelCard(catalog_entry_id=catalog_entry_id, revision=1, **request.model_dump())
            )
        else:
            updates = request.model_dump()
            material = (
                existing.safety_evaluations != updates["safety_evaluations"]
                or existing.bias_assessments != updates["bias_assessments"]
            )
            for field, value in updates.items():
                setattr(existing, field, value)
            existing.revision += 1
            await self.repository.session.flush()
            card = existing
        await publish_model_card_published(
            ModelCardPublishedPayload(
                catalog_entry_id=catalog_entry_id,
                card_id=card.id,
                revision=card.revision,
                material=material,
            ),
            uuid4(),
            self.producer,
        )
        if material and self.trust_service is not None:
            flag = getattr(self.trust_service, "flag_affected_certifications_for_rereview", None)
            if callable(flag):
                await flag(catalog_entry_id)
        response = ModelCardResponse.model_validate(card)
        response.material = material
        return response

    async def get_card(self, catalog_entry_id: UUID) -> ModelCardResponse:
        card = await self.repository.get_card_by_entry_id(catalog_entry_id)
        if card is None:
            raise NotFoundError("MODEL_CARD_NOT_FOUND", "Model card not found")
        return ModelCardResponse.model_validate(card)

    async def get_card_history(self, catalog_entry_id: UUID) -> list[ModelCardResponse]:
        cards = await self.repository.list_card_history(catalog_entry_id)
        return [ModelCardResponse.model_validate(card) for card in cards]
