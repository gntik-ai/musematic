from __future__ import annotations

import asyncio
import logging
import re
from fnmatch import fnmatch
from platform.common.clients.opensearch import AsyncOpenSearchClient
from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.config import PlatformSettings
from platform.marketplace.exceptions import (
    AgentNotFoundError,
    ComparisonRangeError,
    VisibilityDeniedError,
)
from platform.marketplace.repository import MarketplaceRepository
from platform.marketplace.schemas import (
    AgentComparisonResponse,
    AgentComparisonRow,
    AgentListingProjection,
    AggregateRatingSchema,
    ComparisonAttribute,
    MarketplaceSearchRequest,
    MarketplaceSearchResponse,
    QualityProfileSchema,
)
from platform.registry.models import LifecycleStatus
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import httpx

LOGGER = logging.getLogger(__name__)


class MarketplaceSearchService:
    def __init__(
        self,
        *,
        repository: MarketplaceRepository,
        settings: PlatformSettings,
        opensearch: AsyncOpenSearchClient,
        qdrant: AsyncQdrantClient,
        workspaces_service: Any | None,
        registry_service: Any | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.opensearch = opensearch
        self.qdrant = qdrant
        self.workspaces_service = workspaces_service
        self.registry_service = registry_service
        self.rrf_k = settings.memory.rrf_k

    async def search(
        self,
        request: MarketplaceSearchRequest,
        workspace_id: UUID,
        user_id: UUID,
        requesting_agent_id: UUID | None = None,
    ) -> MarketplaceSearchResponse:
        visibility_patterns = await self._get_visibility_patterns(
            workspace_id,
            requesting_agent_id=requesting_agent_id,
        )
        if not request.query:
            documents, total = await self._browse_documents(request, visibility_patterns)
            listings = await self._assemble_listings(documents)
            return MarketplaceSearchResponse(
                results=listings,
                total=total,
                page=request.page,
                page_size=request.page_size,
                query=request.query,
                has_results=bool(listings),
            )

        opensearch_task = self._query_opensearch(request, visibility_patterns)
        qdrant_task = self._query_qdrant(request, visibility_patterns)
        opensearch_hits, qdrant_hits = await asyncio.gather(opensearch_task, qdrant_task)
        merged = self._rrf_merge(opensearch_hits, qdrant_hits)
        if not merged:
            return await self._search_with_registry_fallback(
                request,
                workspace_id,
                user_id,
                requesting_agent_id=requesting_agent_id,
            )
        total = len(merged)
        start = (request.page - 1) * request.page_size
        stop = request.page * request.page_size
        page_items = merged[start:stop]
        documents_by_id = await self._fetch_documents(
            [UUID(item["agent_id"]) for item in page_items]
        )
        listings = await self._assemble_listings(
            [
                dict(documents_by_id[UUID(item["agent_id"])], _relevance_score=item["score"])
                for item in page_items
                if UUID(item["agent_id"]) in documents_by_id
            ]
        )
        if not listings:
            return await self._search_with_registry_fallback(
                request,
                workspace_id,
                user_id,
                requesting_agent_id=requesting_agent_id,
            )
        return MarketplaceSearchResponse(
            results=listings,
            total=total,
            page=request.page,
            page_size=request.page_size,
            query=request.query,
            has_results=bool(listings),
        )

    async def get_listing(
        self,
        agent_id: UUID,
        workspace_id: UUID,
        requesting_agent_id: UUID | None = None,
    ) -> AgentListingProjection:
        visibility_patterns = await self._get_visibility_patterns(
            workspace_id,
            requesting_agent_id=requesting_agent_id,
        )
        document = await self._fetch_document(agent_id)
        profile = await self._resolve_registry_profile_by_id(
            agent_id,
            workspace_id,
            requesting_agent_id=requesting_agent_id,
        )
        if document is None:
            if profile is None:
                raise AgentNotFoundError(agent_id)
            document = self._build_document_from_profile(profile)
        else:
            document = self._merge_document_with_profile_status(document, profile)
        if not self._is_operational_status(document.get("status")):
            raise AgentNotFoundError(agent_id)
        if not self._is_visible(document.get("fqn"), visibility_patterns):
            raise VisibilityDeniedError(agent_id)
        listing = await self._assemble_listing(document)
        return listing

    async def get_listing_by_fqn(
        self,
        namespace: str,
        name: str,
        workspace_id: UUID,
        *,
        actor_id: UUID | None = None,
        requesting_agent_id: UUID | None = None,
    ) -> AgentListingProjection:
        fqn = f"{namespace}:{name}"
        profile = None
        if self.registry_service is not None and hasattr(self.registry_service, "resolve_fqn"):
            try:
                profile = await self.registry_service.resolve_fqn(
                    fqn,
                    workspace_id=workspace_id,
                    actor_id=actor_id,
                    requesting_agent_id=requesting_agent_id,
                )
            except Exception:
                profile = None
        if profile is None:
            raise AgentNotFoundError(fqn)

        document = await self._fetch_document(profile.id)
        if document is None:
            document = self._build_document_from_profile(profile)
        else:
            document = self._merge_document_with_profile_status(document, profile)
        listing = await self._assemble_listing(document)
        if self._profile_status_value(profile) == "decommissioned":
            listing = listing.model_copy(update={"status": "decommissioned", "invocable": False})
        return listing

    async def compare(
        self,
        agent_ids: list[UUID],
        workspace_id: UUID,
        requesting_agent_id: UUID | None = None,
    ) -> AgentComparisonResponse:
        if not 2 <= len(agent_ids) <= 4:
            raise ComparisonRangeError(len(agent_ids))
        listings = await asyncio.gather(
            *(
                self.get_listing(
                    agent_id,
                    workspace_id,
                    requesting_agent_id=requesting_agent_id,
                )
                for agent_id in agent_ids
            )
        )
        compared_rows: list[AgentComparisonRow] = []
        attributes: tuple[tuple[str, str], ...] = (
            ("capabilities", "capabilities"),
            ("maturity_level", "maturity_level"),
            ("trust_tier", "trust_tier"),
            ("certification_status", "certification_status"),
            ("quality_score_avg", "quality_score_avg"),
            ("cost_tier", "cost_tier"),
            ("success_rate", "success_rate"),
            ("user_rating_avg", "user_rating_avg"),
        )
        values_by_attr: dict[str, list[Any]] = {}
        for output_name, listing_attr in attributes:
            resolved: list[Any] = []
            for listing in listings:
                if listing_attr == "quality_score_avg":
                    resolved.append(
                        listing.quality_profile.quality_score_avg
                        if listing.quality_profile is not None
                        else None
                    )
                elif listing_attr == "success_rate":
                    resolved.append(
                        listing.quality_profile.success_rate
                        if listing.quality_profile is not None
                        else None
                    )
                elif listing_attr == "user_rating_avg":
                    resolved.append(
                        listing.aggregate_rating.avg_score
                        if listing.aggregate_rating is not None
                        else None
                    )
                else:
                    resolved.append(getattr(listing, listing_attr))
            values_by_attr[output_name] = resolved

        for index, listing in enumerate(listings):
            compared_rows.append(
                AgentComparisonRow(
                    agent_id=listing.agent_id,
                    fqn=listing.fqn,
                    name=listing.name,
                    capabilities=self._comparison_attribute(values_by_attr["capabilities"], index),
                    maturity_level=self._comparison_attribute(
                        values_by_attr["maturity_level"],
                        index,
                    ),
                    trust_tier=self._comparison_attribute(values_by_attr["trust_tier"], index),
                    certification_status=self._comparison_attribute(
                        values_by_attr["certification_status"],
                        index,
                    ),
                    quality_score_avg=self._comparison_attribute(
                        values_by_attr["quality_score_avg"],
                        index,
                    ),
                    cost_tier=self._comparison_attribute(values_by_attr["cost_tier"], index),
                    success_rate=self._comparison_attribute(values_by_attr["success_rate"], index),
                    user_rating_avg=self._comparison_attribute(
                        values_by_attr["user_rating_avg"],
                        index,
                    ),
                )
            )
        return AgentComparisonResponse(agents=compared_rows, compared_count=len(compared_rows))

    def _build_opensearch_query(
        self,
        request: MarketplaceSearchRequest,
        visibility_patterns: list[str],
    ) -> dict[str, Any]:
        must: list[dict[str, Any]] = []
        filters: list[dict[str, Any]] = []
        if request.query:
            must.append(
                {
                    "multi_match": {
                        "query": request.query,
                        "fields": [
                            "display_name^4",
                            "name^4",
                            "purpose^3",
                            "description^3",
                            "approach^2",
                            "capabilities^2",
                            "role_types^2",
                            "tags",
                            "fqn",
                        ],
                        "type": "best_fields",
                    }
                }
            )
        else:
            must.append({"match_all": {}})
        filters.extend(self._facet_filters(request))
        filters.append(
            {"bool": {"must_not": [{"terms": {"status": ["archived", "decommissioned"]}}]}}
        )
        if visibility_patterns and visibility_patterns != ["*"]:
            filters.append(
                {
                    "bool": {
                        "should": [
                            {"wildcard": {"fqn": {"value": pattern.replace("*", "*")}}}
                            for pattern in visibility_patterns
                        ],
                        "minimum_should_match": 1,
                    }
                }
            )
        return {"bool": {"must": must, "filter": filters}}

    async def _query_opensearch(
        self,
        request: MarketplaceSearchRequest,
        visibility_patterns: list[str],
    ) -> list[dict[str, Any]]:
        client = await self.opensearch._ensure_client()
        response = await client.search(
            index=self.settings.registry.search_index,
            body={
                "query": self._build_opensearch_query(request, visibility_patterns),
                "size": 50,
            },
        )
        hits = response.get("hits", {}).get("hits", [])
        results: list[dict[str, Any]] = []
        for rank, hit in enumerate(hits, start=1):
            source = dict(hit.get("_source", {}))
            agent_id = source.get("agent_profile_id") or source.get("agent_id") or hit.get("_id")
            if agent_id is None:
                continue
            if not self._is_operational_status(source.get("status")):
                continue
            if not self._is_visible(source.get("fqn"), visibility_patterns):
                continue
            results.append(
                {
                    "agent_id": str(agent_id),
                    "rank": rank,
                    "score": float(hit.get("_score") or 0.0),
                    "source": source,
                }
            )
        return results

    async def _query_qdrant(
        self,
        request: MarketplaceSearchRequest,
        visibility_patterns: list[str],
    ) -> list[dict[str, Any]]:
        try:
            vector = await self._embed_text(request.query)
        except (httpx.HTTPError, ValueError) as exc:
            LOGGER.warning(
                "Marketplace semantic search disabled for query %r: %s",
                request.query,
                exc,
            )
            return []

        try:
            results = await self.qdrant.search_vectors(
                self.settings.registry.embeddings_collection,
                query_vector=vector,
                limit=50,
                filter=None,
            )
        except Exception as exc:
            LOGGER.warning(
                "Marketplace vector search disabled for query %r: %s",
                request.query,
                exc,
            )
            return []

        filtered = [
            item
            for item in results
            if self._is_operational_status(item.get("payload", {}).get("status"))
            and self._is_visible(item.get("payload", {}).get("fqn"), visibility_patterns)
            and self._matches_facets(item.get("payload", {}), request)
        ]
        ranked: list[dict[str, Any]] = []
        for rank, item in enumerate(filtered, start=1):
            ranked.append(
                {
                    "agent_id": str(item["id"]),
                    "rank": rank,
                    "score": float(item.get("score") or 0.0),
                    "source": item.get("payload", {}),
                }
            )
        return ranked

    async def _browse_documents(
        self,
        request: MarketplaceSearchRequest,
        visibility_patterns: list[str],
    ) -> tuple[list[dict[str, Any]], int]:
        client = await self.opensearch._ensure_client()
        response = await client.search(
            index=self.settings.registry.search_index,
            body={
                "query": self._build_opensearch_query(request, visibility_patterns),
                "sort": [
                    {"invocation_count_30d": {"order": "desc", "unmapped_type": "long"}},
                    {"display_name.keyword": {"order": "asc", "unmapped_type": "keyword"}},
                ],
                "size": max(50, request.page * request.page_size),
            },
        )
        hits = response.get("hits", {}).get("hits", [])
        visible_docs = [
            dict(hit.get("_source", {}), _id=hit.get("_id"))
            for hit in hits
            if self._is_operational_status(hit.get("_source", {}).get("status"))
            and self._is_visible(hit.get("_source", {}).get("fqn"), visibility_patterns)
        ]
        total = len(visible_docs)
        page_docs = visible_docs[
            (request.page - 1) * request.page_size : request.page * request.page_size
        ]
        return page_docs, total

    async def _assemble_listings(
        self,
        documents: list[dict[str, Any]],
    ) -> list[AgentListingProjection]:
        if not documents:
            return []
        agent_ids = [self._extract_agent_id(document) for document in documents]
        quality_by_agent, rating_by_agent, certification_by_agent = await asyncio.gather(
            self.repository.get_quality_aggregates(agent_ids),
            self.repository.get_rating_summaries(agent_ids),
            self.repository.get_active_certification_statuses(agent_ids),
        )
        return [
            self._assemble_listing_from_cache(
                document,
                quality_by_agent.get(self._extract_agent_id(document)),
                rating_by_agent.get(self._extract_agent_id(document)),
                certification_by_agent.get(self._extract_agent_id(document)),
            )
            for document in documents
        ]

    async def _assemble_listing(self, document: dict[str, Any]) -> AgentListingProjection:
        agent_id = self._extract_agent_id(document)
        quality, rating, certification_status = await asyncio.gather(
            self.repository.get_quality_aggregate(agent_id),
            self.repository.get_rating_summary(agent_id),
            self.repository.get_active_certification_status(agent_id),
        )
        return self._assemble_listing_from_cache(document, quality, rating, certification_status)

    def _assemble_listing_from_cache(
        self,
        document: dict[str, Any],
        quality: Any | None,
        rating: dict[str, Any] | None,
        certification_status: str | None = None,
    ) -> AgentListingProjection:
        agent_id = self._extract_agent_id(document)
        effective_certification_status = self._effective_certification_status(
            certification_status,
            document.get("certification_status"),
            quality.certification_status if quality is not None else None,
        )
        quality_profile = None
        if quality is not None:
            quality_profile = QualityProfileSchema(
                agent_id=agent_id,
                has_data=quality.has_data,
                success_rate=quality.success_rate if quality.has_data else None,
                quality_score_avg=quality.quality_score_avg if quality.has_data else None,
                self_correction_rate=quality.self_correction_rate if quality.has_data else None,
                satisfaction_avg=quality.satisfaction_avg if quality.has_data else None,
                satisfaction_count=quality.satisfaction_count,
                certification_compliance=effective_certification_status,
                last_updated_at=quality.data_source_last_updated_at,
                source_unavailable=quality.source_unavailable_since is not None,
            )
        aggregate_rating = None
        if rating is not None:
            aggregate_rating = AggregateRatingSchema(
                avg_score=rating.get("avg_score"),
                review_count=int(rating.get("review_count") or 0),
            )
        name = (
            document.get("display_name")
            or document.get("name")
            or document.get("local_name")
            or document.get("fqn")
            or str(agent_id)
        )
        description = document.get("description") or document.get("purpose") or ""
        status = str(document.get("status") or "published")
        return AgentListingProjection(
            agent_id=agent_id,
            fqn=str(document.get("fqn") or ""),
            name=str(name),
            description=str(description),
            capabilities=list(document.get("capabilities") or document.get("role_types") or []),
            tags=list(document.get("tags") or []),
            maturity_level=int(document.get("maturity_level") or 0),
            trust_tier=str(document.get("trust_tier") or "unverified"),
            certification_status=effective_certification_status,
            cost_tier=str(document.get("cost_tier") or "free"),
            status=status,
            invocable=status != "decommissioned",
            quality_profile=quality_profile,
            aggregate_rating=aggregate_rating,
            relevance_score=_as_float(document.get("_relevance_score")),
        )

    async def _search_with_registry_fallback(
        self,
        request: MarketplaceSearchRequest,
        workspace_id: UUID,
        user_id: UUID,
        *,
        requesting_agent_id: UUID | None = None,
    ) -> MarketplaceSearchResponse:
        documents, total = await self._search_registry_profiles(
            request,
            workspace_id,
            user_id,
            requesting_agent_id=requesting_agent_id,
        )
        listings = await self._assemble_listings(documents)
        return MarketplaceSearchResponse(
            results=listings,
            total=total,
            page=request.page,
            page_size=request.page_size,
            query=request.query,
            has_results=bool(listings),
        )

    async def _search_registry_profiles(
        self,
        request: MarketplaceSearchRequest,
        workspace_id: UUID,
        user_id: UUID,
        *,
        requesting_agent_id: UUID | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        if self.registry_service is None or not hasattr(self.registry_service, "list_agents"):
            return [], 0
        params = SimpleNamespace(
            workspace_id=workspace_id,
            fqn_pattern=None,
            keyword=None,
            maturity_min=request.maturity_level_min or 0,
            status=LifecycleStatus.published,
            limit=200,
            offset=0,
        )
        try:
            response = await self.registry_service.list_agents(
                params,
                requesting_agent_id=requesting_agent_id,
                actor_id=user_id,
            )
        except Exception:
            LOGGER.warning(
                "Registry search fallback failed for query %r", request.query, exc_info=True
            )
            return [], 0

        ranked_documents: list[dict[str, Any]] = []
        for profile in getattr(response, "items", []):
            score = self._registry_query_score(profile, request.query)
            if score <= 0:
                continue
            document = self._build_document_from_profile(profile)
            if not self._matches_facets(document, request):
                continue
            ranked_documents.append(dict(document, _relevance_score=score))

        ranked_documents.sort(
            key=lambda item: (
                -(_as_float(item.get("_relevance_score")) or 0.0),
                str(item.get("name") or item.get("display_name") or item.get("fqn") or ""),
            )
        )
        total = len(ranked_documents)
        start = (request.page - 1) * request.page_size
        stop = request.page * request.page_size
        return ranked_documents[start:stop], total

    def _registry_query_score(self, profile: Any, query: str) -> float:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return 0.0
        tokens = [token for token in re.split(r"[^a-z0-9]+", normalized_query) if token]
        if not tokens:
            return 0.0
        haystacks = [
            str(getattr(profile, "fqn", "") or ""),
            str(getattr(profile, "display_name", "") or ""),
            str(getattr(profile, "purpose", "") or ""),
            str(getattr(profile, "approach", "") or ""),
            " ".join(str(item) for item in getattr(profile, "tags", []) or []),
            " ".join(str(item) for item in getattr(profile, "role_types", []) or []),
        ]
        combined = " ".join(haystacks).lower()
        if not combined:
            return 0.0
        score = 0.0
        if normalized_query in combined:
            score += 5.0
        score += sum(1.0 for token in tokens if token in combined)
        return score

    async def _fetch_document(self, agent_id: UUID) -> dict[str, Any] | None:
        documents = await self._fetch_documents([agent_id])
        return documents.get(agent_id)

    async def _fetch_documents(self, agent_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
        if not agent_ids:
            return {}
        client = await self.opensearch._ensure_client()
        response = await client.search(
            index=self.settings.registry.search_index,
            body={
                "query": {"terms": {"agent_profile_id": [str(agent_id) for agent_id in agent_ids]}},
                "size": len(agent_ids),
            },
        )
        docs: dict[UUID, dict[str, Any]] = {}
        for hit in response.get("hits", {}).get("hits", []):
            source = dict(hit.get("_source", {}))
            source["_id"] = hit.get("_id")
            docs[self._extract_agent_id(source)] = source
        return docs

    async def _resolve_registry_profile_by_id(
        self,
        agent_id: UUID,
        workspace_id: UUID,
        *,
        requesting_agent_id: UUID | None = None,
    ) -> Any | None:
        if self.registry_service is None:
            return None
        if hasattr(self.registry_service, "get_agent"):
            try:
                profile = await self.registry_service.get_agent(
                    workspace_id,
                    agent_id,
                    requesting_agent_id=requesting_agent_id,
                )
            except Exception:
                profile = None
            if profile is not None:
                return profile
        repository = getattr(self.registry_service, "repository", None)
        if repository is None or not hasattr(repository, "get_agent_by_id_any"):
            return None
        try:
            return await repository.get_agent_by_id_any(agent_id)
        except Exception:
            return None

    def _build_document_from_profile(self, profile: Any) -> dict[str, Any]:
        return {
            "agent_profile_id": str(profile.id),
            "fqn": profile.fqn,
            "display_name": profile.display_name,
            "name": profile.display_name or profile.fqn,
            "description": profile.purpose,
            "purpose": profile.purpose,
            "capabilities": list(getattr(profile, "role_types", [])),
            "role_types": list(getattr(profile, "role_types", [])),
            "tags": list(getattr(profile, "tags", [])),
            "maturity_level": int(getattr(profile, "maturity_level", 0) or 0),
            "certification_status": "uncertified",
            "cost_tier": "free",
            "status": self._profile_status_value(profile),
        }

    def _merge_document_with_profile_status(
        self,
        document: dict[str, Any],
        profile: Any | None,
    ) -> dict[str, Any]:
        if profile is None:
            return document
        merged = dict(document)
        merged["status"] = self._profile_status_value(profile)
        return merged

    def _profile_status_value(self, profile: Any) -> str:
        status = getattr(profile, "status", None)
        if status is not None and hasattr(status, "value"):
            return str(status.value)
        return str(status or "published")

    async def _get_visibility_patterns(
        self,
        workspace_id: UUID,
        requesting_agent_id: UUID | None = None,
    ) -> list[str]:
        if self.settings.visibility.zero_trust_enabled and requesting_agent_id is not None:
            if self.registry_service is None or not hasattr(
                self.registry_service,
                "resolve_effective_visibility",
            ):
                return []
            effective = await self.registry_service.resolve_effective_visibility(
                requesting_agent_id,
                workspace_id,
            )
            return list(getattr(effective, "agent_patterns", []))
        if self.workspaces_service is None:
            return ["*"]
        getter = getattr(self.workspaces_service, "get_visibility_config", None)
        if getter is not None:
            response = await getter(workspace_id)
            patterns = list(getattr(response, "visibility_agents", response or []))
            return patterns or ["*"]
        for name in ("get_workspace_visibility_grant", "get_visibility_grant"):
            getter = getattr(self.workspaces_service, name, None)
            if getter is None:
                continue
            response = await getter(workspace_id)
            if response is None:
                return ["*"]
            patterns = list(getattr(response, "visibility_agents", []))
            return patterns or ["*"]
        return ["*"]

    async def _embed_text(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.settings.registry.embedding_api_url,
                json={"input": text},
            )
            response.raise_for_status()
            payload = response.json()
        for candidate in (
            payload.get("embedding"),
            payload.get("vector"),
        ):
            if isinstance(candidate, list):
                return [float(item) for item in candidate]
        data = payload.get("data")
        if isinstance(data, list) and data:
            embedding = data[0].get("embedding")
            if isinstance(embedding, list):
                return [float(item) for item in embedding]
        raise ValueError("Embedding response did not contain a vector.")

    def _facet_filters(self, request: MarketplaceSearchRequest) -> list[dict[str, Any]]:
        filters: list[dict[str, Any]] = []
        if request.tags:
            filters.append({"terms": {"tags": request.tags}})
        if request.capabilities:
            filters.append({"terms": {"capabilities": request.capabilities}})
        if request.maturity_level_min is not None or request.maturity_level_max is not None:
            maturity_range: dict[str, Any] = {}
            if request.maturity_level_min is not None:
                maturity_range["gte"] = request.maturity_level_min
            if request.maturity_level_max is not None:
                maturity_range["lte"] = request.maturity_level_max
            filters.append({"range": {"maturity_level": maturity_range}})
        if request.trust_tier:
            filters.append({"terms": {"trust_tier": request.trust_tier}})
        if request.certification_status:
            filters.append({"terms": {"certification_status": request.certification_status}})
        if request.cost_tier:
            filters.append({"terms": {"cost_tier": request.cost_tier}})
        return filters

    def _matches_facets(self, payload: dict[str, Any], request: MarketplaceSearchRequest) -> bool:
        if request.tags and not set(request.tags).intersection(set(payload.get("tags", []))):
            return False
        capabilities = payload.get("capabilities") or payload.get("role_types") or []
        if request.capabilities and not set(request.capabilities).intersection(set(capabilities)):
            return False
        maturity_level = int(payload.get("maturity_level") or 0)
        if request.maturity_level_min is not None and maturity_level < request.maturity_level_min:
            return False
        if request.maturity_level_max is not None and maturity_level > request.maturity_level_max:
            return False
        if request.trust_tier and payload.get("trust_tier") not in set(request.trust_tier):
            return False
        if request.certification_status and payload.get("certification_status") not in set(
            request.certification_status
        ):
            return False
        if request.cost_tier and payload.get("cost_tier") not in set(request.cost_tier):
            return False
        return True

    def _rrf_merge(
        self,
        opensearch_hits: list[dict[str, Any]],
        qdrant_hits: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for source_name, hits in (("opensearch", opensearch_hits), ("qdrant", qdrant_hits)):
            for item in hits:
                agent_id = item["agent_id"]
                record = merged.setdefault(agent_id, {"agent_id": agent_id, "score": 0.0})
                record[source_name] = item
                record["score"] += 1.0 / (self.rrf_k + item["rank"])
        return sorted(
            merged.values(),
            key=lambda item: (-float(item["score"]), item["agent_id"]),
        )

    def _comparison_attribute(self, values: list[Any], index: int) -> ComparisonAttribute:
        normalized = [self._normalize_for_compare(value) for value in values]
        differs = len(set(normalized)) > 1
        return ComparisonAttribute(value=values[index], differs=differs)

    def _effective_certification_status(self, *candidates: Any) -> str:
        normalized = [
            item
            for item in (_normalize_certification_status(candidate) for candidate in candidates)
            if item is not None
        ]
        for item in normalized:
            if item != "uncertified":
                return item
        return normalized[0] if normalized else "uncertified"

    def _normalize_for_compare(self, value: Any) -> str:
        if isinstance(value, list):
            return "|".join(sorted(str(item) for item in value))
        return str(value)

    @staticmethod
    def _is_operational_status(status: Any) -> bool:
        return str(status or "published") not in {"archived", "decommissioned"}

    def _is_visible(self, fqn: Any, visibility_patterns: list[str]) -> bool:
        if not isinstance(fqn, str):
            return False
        if visibility_patterns == ["*"]:
            return True
        return any(fnmatch(fqn, pattern) for pattern in visibility_patterns)

    def _extract_agent_id(self, document: dict[str, Any]) -> UUID:
        candidate = (
            document.get("agent_profile_id") or document.get("agent_id") or document.get("_id")
        )
        return UUID(str(candidate))


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _normalize_certification_status(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None
