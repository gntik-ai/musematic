from __future__ import annotations

from platform.common.models.base import Base
from platform.evaluation.models import EvaluationRun
from platform.fleets.models import Fleet
from platform.policies.models import PolicyPolicy
from platform.registry.models import AgentProfile
from platform.trust.models import TrustCertification
from platform.workflows.models import WorkflowDefinition
from platform.workspaces.models import Workspace

_MODEL_TO_ENTITY_TYPE: dict[type[Base], str] = {
    Workspace: "workspace",
    AgentProfile: "agent",
    Fleet: "fleet",
    WorkflowDefinition: "workflow",
    PolicyPolicy: "policy",
    TrustCertification: "certification",
    EvaluationRun: "evaluation_run",
}

_ENTITY_TYPE_TO_MODEL: dict[str, type[Base]] = {
    entity_type: model for model, entity_type in _MODEL_TO_ENTITY_TYPE.items()
}


def get_entity_type_string(model: type[Base]) -> str:
    return _MODEL_TO_ENTITY_TYPE[model]


def get_entity_class(entity_type: str) -> type[Base]:
    return _ENTITY_TYPE_TO_MODEL[entity_type]

