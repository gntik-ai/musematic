__all__ = ["get_interactions_service"]


def __getattr__(name: str) -> object:
    if name == "get_interactions_service":
        from platform.interactions.dependencies import get_interactions_service

        return get_interactions_service
    raise AttributeError(name)
