from collections.abc import Sequence

from yakoon.base.commands import Command, CommandSet

from .cmd_demo_ask import CmdDemoAskSimple
from .cmd_demo_ask_validate import CmdDemoAskValidateSimple
from .cmd_demo_delay import CmdDemoDelay
from .cmd_demo_projector import CmdDemoProjector
from .cmd_demo_receive import CmdDemoReceiveSimple
from .cmd_demo_send import CmdDemSendSimple
from .cmd_demo_subflow import CmdDemoSubflow


class DemoCommands(CommandSet):

    group = "demo1"

    @classmethod
    def commands(cls) -> Sequence[type[Command]]:
        return [
            CmdDemoAskSimple,
            CmdDemoAskValidateSimple,
            CmdDemoDelay,
            CmdDemoProjector,
            CmdDemoReceiveSimple,
            CmdDemoSubflow,
            CmdDemSendSimple,
        ]
