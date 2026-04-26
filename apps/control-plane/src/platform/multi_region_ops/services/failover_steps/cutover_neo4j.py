from __future__ import annotations

from platform.multi_region_ops.services.failover_steps.generic import NamedNoopStepAdapter


class CutoverNeo4jStepAdapter(NamedNoopStepAdapter):
    def __init__(self) -> None:
        super().__init__("cutover_neo4j", "Cut over Neo4j")
