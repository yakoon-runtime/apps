from collections.abc import Sequence

from yakoon.base.commands import Command, CommandSet

from .cmd_demo_delay import CmdDemoDelaySimple
from .cmd_demo_focus import CmdDemoFocusSimple
from .cmd_demo_present import CmdDemoPresent
from .cmd_demo_receive import CmdDemoReceiveSimple
from .cmd_demo_send import CmdDemSendSimple


class DemoCommandsDsl(CommandSet):

    group = "dsl"

    @classmethod
    def commands(cls) -> Sequence[type[Command]]:
        return [
            CmdDemoDelaySimple,
            CmdDemoFocusSimple,
            CmdDemoPresent,
            CmdDemoReceiveSimple,
            CmdDemSendSimple,
        ]
