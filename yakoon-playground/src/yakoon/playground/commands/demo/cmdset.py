from collections.abc import Sequence

from yakoon.base.commands import Command, CommandSet

from .cmd_demo_delay import CmdDemoDelay
from .cmd_demo_focus import CmdDemoAskSimple
from .cmd_demo_projector import CmdDemoProjector
from .cmd_demo_receive import CmdDemoReceiveSimple
from .cmd_demo_send import CmdDemSendSimple
from .cmd_demo_subflow import CmdDemoSubflow
from .cmd_demo_validate import CmdDemoValidateSimple


class DemoCommands(CommandSet):

    group = "demo1"

    @classmethod
    def commands(cls) -> Sequence[type[Command]]:
        return [
            CmdDemoAskSimple,
            CmdDemoValidateSimple,
            CmdDemoDelay,
            CmdDemoProjector,
            CmdDemoReceiveSimple,
            CmdDemoSubflow,
            CmdDemSendSimple,
        ]
