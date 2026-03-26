from collections.abc import Sequence

from yakoon.base.runtime.commands import Command, CommandSet

from .cmd_ask import CmdUseAsk
from .cmd_delay import CmdDelay
from .cmd_sub import CmdSub
from .cmd_use_pres import CmdUsePresenter


class CoreCommands(CommandSet):

    group = "core"

    @classmethod
    def commands(cls) -> Sequence[type[Command]]:
        return [
            CmdDelay,
            CmdUsePresenter,
            CmdUseAsk,
            CmdSub,
        ]
