"""Musematic platform package.

This package name intentionally matches the repository's target import path.
To avoid breaking third-party libraries that import the stdlib `platform`
module, proxy the stdlib module's attributes from here.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sysconfig


def _load_stdlib_platform() -> object:
    stdlib_dir = sysconfig.get_path("stdlib")
    spec = importlib.machinery.PathFinder.find_spec("platform", [stdlib_dir])
    if spec is None or spec.loader is None:
        raise ImportError("Unable to load stdlib platform module")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_stdlib_platform = _load_stdlib_platform()

for _name in dir(_stdlib_platform):
    if _name.startswith("__") and _name not in {"__all__", "__doc__"}:
        continue
    globals().setdefault(_name, getattr(_stdlib_platform, _name))

