from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from yakoon.base.api.controller import Controller, ResourceReferences
from yakoon.office.commands.cmdset import MailingCommands

if TYPE_CHECKING:
    from yakoon.base.api import CommandSet


class OfficeMailingCoreController(Controller):
    """Controller for the Office Mailing domain.

    Provides:
        - Mailing-related commands
        - Template root under yakoon.office.mailing:core
    """

    id: str = "office.mailing"

    resources = ResourceReferences(
        package="yakoon.office.mailing",
    )

    @property
    def commandsets(self) -> Sequence[type[CommandSet]]:
        """Command sets exported by this controller."""
        return (MailingCommands,)
