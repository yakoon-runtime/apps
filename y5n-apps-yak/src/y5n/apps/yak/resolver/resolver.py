from __future__ import annotations

from collections.abc import Callable

from y5n.apps.yak.distribution.models import (
    Distribution,
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
    ) -> tuple[list[PackName], list[ToolReference]]:
        seen: set[PackName] = set()
        order: list[PackName] = []
        tools: list[ToolReference] = []
        self._resolve_tree(distribution, seen, order, tools)
        return order, tools

    def _resolve_tree(
        self,
        dist: Distribution,
        seen: set[PackName],
        order: list[PackName],
        tools: list[ToolReference],
    ) -> None:
        for sub_ref in dist.distributions:
            sub = self._resolve_distribution(sub_ref.name)
            if sub is not None:
                self._resolve_tree(sub, seen, order, tools)

        tools.extend(dist.tools)

        for mount in dist.mounts:
            if mount.source not in seen:
                seen.add(PackName(mount.source))
                order.append(PackName(mount.source))
