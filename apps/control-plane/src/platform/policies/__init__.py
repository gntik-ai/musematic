__all__ = [
    "get_memory_write_gate_service",
    "get_policy_service",
    "get_tool_gateway_service",
]


def __getattr__(name: str) -> object:
    if name in __all__:
        from platform.policies import dependencies

        return getattr(dependencies, name)
    raise AttributeError(name)
