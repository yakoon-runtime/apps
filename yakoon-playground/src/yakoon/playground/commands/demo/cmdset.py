from collections.abc import Sequence

from yakoon.base.runtime.commands import Command, CommandSet

from .cmd_demo_ask import CmdDemoAskSimple
from .cmd_demo_delay import CmdDemoDelay
from .cmd_demo_presenter import CmdDemoPresenter
from .cmd_demo_subflow import CmdDemoSubflow


class DemoCommands(CommandSet):

    group = "demo1"

    @classmethod
    def commands(cls) -> Sequence[type[Command]]:
        return [
            CmdDemoAskSimple,
            CmdDemoDelay,
            CmdDemoPresenter,
            CmdDemoSubflow,
        ]
