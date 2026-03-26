from __future__ import annotations

from collections.abc import Sequence

from yakoon.base.runtime.commands.commandset import CommandSet
from yakoon.base.runtime.controllers import Controller, ResourceReferences
from yakoon.office.commands.cmdset import MailingCommands


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
