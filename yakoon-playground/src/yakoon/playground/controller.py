from __future__ import annotations

from collections.abc import Sequence

from yakoon.base.runtime.commands.commandset import CommandSet
from yakoon.base.runtime.controllers import Controller, ResourceReferences

from .commands.demo.cmdset import DemoCommands


class Demo1Controller(Controller):
    """Playground controller.

    This controller provides the default interactive environment.
    """

    id: str = "demo"
    is_listed: bool = True
    is_activatable: bool = True

    resources = ResourceReferences(
        package="yakoon.playground",
    )

    @property
    def commandsets(self) -> Sequence[type[CommandSet]]:
        return (DemoCommands,)
