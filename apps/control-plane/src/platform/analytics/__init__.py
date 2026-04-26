__all__ = ["get_analytics_service"]


def __getattr__(name: str) -> object:
    if name == "get_analytics_service":
        from platform.analytics.dependencies import get_analytics_service

        return get_analytics_service
    raise AttributeError(name)
