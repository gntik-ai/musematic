"""Compatibility shim for direct module execution from apps/control-plane."""

from __future__ import annotations

from pathlib import Path

src_platform = Path(__file__).resolve().parent.parent / "src" / "platform"
__path__ = [str(src_platform)]

src_init = src_platform / "__init__.py"
exec(compile(src_init.read_text(encoding="utf-8"), str(src_init), "exec"), globals())
