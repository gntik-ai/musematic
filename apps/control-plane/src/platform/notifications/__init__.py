__all__ = ["router"]


def __getattr__(name: str) -> object:
    if name == "router":
        from platform.notifications.router import router

        return router
    raise AttributeError(name)
