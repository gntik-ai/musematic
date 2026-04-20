from __future__ import annotations

from platform.common.clients.neo4j import AsyncNeo4jClient
from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.clients.sandbox_manager import SandboxManagerClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.discovery.critique.evaluator import CritiqueEvaluator
from platform.discovery.events import DiscoveryEventPublisher
from platform.discovery.experiment.designer import ExperimentDesigner
from platform.discovery.gde.cycle import GDECycleOrchestrator
from platform.discovery.provenance.graph import ProvenanceGraph
from platform.discovery.proximity.clustering import ProximityClustering
from platform.discovery.proximity.embeddings import HypothesisEmbedder
from platform.discovery.proximity.graph import ProximityGraphService
from platform.discovery.repository import DiscoveryRepository
from platform.discovery.service import DiscoveryService
from platform.discovery.tournament.comparator import TournamentComparator
from platform.discovery.tournament.elo import EloRatingEngine
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def build_discovery_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    redis_client: AsyncRedisClient,
    qdrant: AsyncQdrantClient | None,
    neo4j: AsyncNeo4jClient | None,
    sandbox_client: SandboxManagerClient | None,
) -> DiscoveryService:
    repository = DiscoveryRepository(session, redis_client)
    publisher = DiscoveryEventPublisher(producer)
    elo_engine = EloRatingEngine(
        redis=redis_client,
        repository=repository,
        default_score=settings.discovery.elo_default_score,
        k_factor=settings.discovery.elo_k_factor,
    )
    tournament = TournamentComparator(
        repository=repository,
        elo_engine=elo_engine,
        publisher=publisher,
        workflow_service=None,
    )
    critique_evaluator = CritiqueEvaluator(
        repository=repository,
        publisher=publisher,
        workflow_service=None,
    )
    provenance_graph = ProvenanceGraph(neo4j)
    embedder = HypothesisEmbedder(settings=settings, qdrant=qdrant, repository=repository)
    proximity_clustering = ProximityClustering(
        settings=settings,
        repository=repository,
        embedder=embedder,
        publisher=publisher,
    )
    proximity_graph_service = ProximityGraphService(
        embedder=embedder,
        clustering=proximity_clustering,
        repository=repository,
        event_publisher=publisher,
        settings=settings.discovery,
    )
    experiment_designer = ExperimentDesigner(
        repository=repository,
        publisher=publisher,
        settings=settings,
        workflow_service=None,
        policy_service=None,
        sandbox_client=sandbox_client,
        provenance_graph=provenance_graph,
        elo_engine=elo_engine,
    )
    gde_orchestrator = GDECycleOrchestrator(
        repository=repository,
        settings=settings,
        publisher=publisher,
        tournament=tournament,
        critique_evaluator=critique_evaluator,
        workflow_service=None,
        proximity_graph_service=proximity_graph_service,
    )
    return DiscoveryService(
        repository=repository,
        settings=settings,
        publisher=publisher,
        elo_engine=elo_engine,
        tournament=tournament,
        critique_evaluator=critique_evaluator,
        gde_orchestrator=gde_orchestrator,
        experiment_designer=experiment_designer,
        provenance_graph=provenance_graph,
        proximity_clustering=proximity_clustering,
        proximity_graph_service=proximity_graph_service,
    )


async def get_discovery_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> DiscoveryService:
    return build_discovery_service(
        session=session,
        settings=cast(PlatformSettings, request.app.state.settings),
        producer=cast(EventProducer | None, request.app.state.clients.get("kafka")),
        redis_client=cast(AsyncRedisClient, request.app.state.clients["redis"]),
        qdrant=cast(AsyncQdrantClient | None, request.app.state.clients.get("qdrant")),
        neo4j=cast(AsyncNeo4jClient | None, request.app.state.clients.get("neo4j")),
        sandbox_client=cast(
            SandboxManagerClient | None,
            request.app.state.clients.get("sandbox_manager"),
        ),
    )


DiscoveryServiceDep = Annotated[DiscoveryService, Depends(get_discovery_service)]
