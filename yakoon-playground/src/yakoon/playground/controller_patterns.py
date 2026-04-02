from __future__ import annotations

from collections.abc import Sequence

from yakoon.base.commands import CommandSet
from yakoon.base.controllers import Controller, ResourceReferences

from .commands.patterns.cmdset import DemoCommandsPatterns


class DemoControllerPatterns(Controller):
    """Playground controller.

    This controller provides the default interactive environment.
    """

    id: str = "demo.patterns"
    is_listed: bool = True
    is_activatable: bool = True

    resources = ResourceReferences(
        package="yakoon.playground",
    )

    @property
    def commandsets(self) -> Sequence[type[CommandSet]]:
        return (DemoCommandsPatterns,)
