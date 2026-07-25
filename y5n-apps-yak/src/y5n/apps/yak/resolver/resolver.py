from __future__ import annotations

from collections.abc import Callable

from y5n.apps.yak.distribution.models import (
    Distribution,
    Mount,
    PackName,
    ToolReference,
)


class Resolver:
    def __init__(
        self,
        resolve_distribution: Callable[[str], Distribution | None],
    ) -> None:
        self._resolve_distribution = resolve_distribution

    def resolve(
        self,
        distribution: Distribution,
    ) -> tuple[list[PackName], list[Mount], list[ToolReference]]:
        seen: set[PackName] = set()
        order: list[PackName] = []
        mounts: list[Mount] = []
        tools: list[ToolReference] = []
        self._resolve_tree(distribution, seen, order, mounts, tools)
        return order, mounts, tools

    def _resolve_tree(
        self,
        dist: Distribution,
        seen: set[PackName],
        order: list[PackName],
        mounts: list[Mount],
        tools: list[ToolReference],
    ) -> None:
        for sub_ref in dist.distributions:
            sub = self._resolve_distribution(sub_ref.name)
            if sub is not None:
                self._resolve_tree(sub, seen, order, mounts, tools)

        mounts.extend(dist.mounts)
        tools.extend(dist.tools)

        for mount in dist.mounts:
            if mount.pack not in seen:
                seen.add(mount.pack)
                order.append(mount.pack)
