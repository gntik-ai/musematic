from __future__ import annotations

import argparse
import asyncio
import importlib
import os
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class SeedRunSummary:
    seeded: dict[str, int]
    skipped: dict[str, int]


class SeederBase(ABC):
    name: str
    dependencies: tuple[str, ...] = ()

    @abstractmethod
    async def seed(self) -> SeedRunSummary:
        raise NotImplementedError

    @abstractmethod
    async def reset(self) -> dict[str, int]:
        raise NotImplementedError


DEFAULT_SEEDER_MODULES: tuple[str, ...] = (
    'users',
    'namespaces',
    'agents',
    'tools',
    'policies',
    'certifiers',
    'fleets',
    'workspace_goals',
)


def _discover_seeders() -> list[SeederBase]:
    configured = os.environ.get('E2E_SEEDER_MODULES')
    module_names = [item.strip() for item in configured.split(',')] if configured else list(DEFAULT_SEEDER_MODULES)
    seeders: list[SeederBase] = []
    for module_name in module_names:
        if not module_name:
            continue
        try:
            module = importlib.import_module(f'seeders.{module_name}')
        except ModuleNotFoundError:
            continue
        builder = getattr(module, 'build_seeder', None)
        if callable(builder):
            seeder = builder()
        else:
            seeder_cls = getattr(module, 'Seeder', None)
            if seeder_cls is None:
                continue
            seeder = seeder_cls()
        if isinstance(seeder, SeederBase):
            seeders.append(seeder)
    return _topological_sort(seeders)


def _topological_sort(seeders: Iterable[SeederBase]) -> list[SeederBase]:
    remaining = {seeder.name: seeder for seeder in seeders}
    ordered: list[SeederBase] = []
    while remaining:
        progressed = False
        for name, seeder in list(remaining.items()):
            if all(dep not in remaining for dep in seeder.dependencies):
                ordered.append(seeder)
                remaining.pop(name)
                progressed = True
        if not progressed:
            ordered.extend(remaining.values())
            break
    return ordered


async def run_seeders(*, reset: bool = False) -> dict[str, Any]:
    seeded: dict[str, int] = {}
    skipped: dict[str, int] = {}
    deleted: dict[str, int] = {}
    seeders = _discover_seeders()
    for seeder in seeders:
        if reset:
            deleted[seeder.name] = sum((await seeder.reset()).values())
            continue
        summary = await seeder.seed()
        seeded[seeder.name] = sum(summary.seeded.values())
        skipped[seeder.name] = sum(summary.skipped.values())
    if reset:
        return {'deleted': deleted}
    return {'seeded': seeded, 'skipped': skipped}


def main() -> None:
    parser = argparse.ArgumentParser(description='Run E2E seeders')
    parser.add_argument('--all', action='store_true', help='Run all discovered seeders')
    parser.add_argument('--reset', action='store_true', help='Reset discovered seeders instead of seeding')
    args = parser.parse_args()
    if not args.all:
        parser.error('--all is required')
    result = asyncio.run(run_seeders(reset=args.reset))
    print(result)


if __name__ == '__main__':
    main()
