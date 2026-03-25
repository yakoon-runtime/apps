from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from yakoon.base.api.controller import Controller, ResourceReferences

from .commands.core.cmdset import CoreCommands

if TYPE_CHECKING:
    from yakoon.base.api import CommandSet


class PlaygroundController(Controller):
    """Playground controller.

    This controller provides the default interactive environment.
    """

    id: str = "pg"
    is_listed: bool = True
    is_activatable: bool = True

    resources = ResourceReferences(
        package="yakoon.playground",
    )

    @property
    def commandsets(self) -> Sequence[type[CommandSet]]:
        return (CoreCommands,)
