__all__ = ["get_fleet_service"]


def __getattr__(name: str) -> object:
    if name in __all__:
        from platform.fleets import dependencies

        return getattr(dependencies, name)
    raise AttributeError(name)
