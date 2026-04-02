from collections.abc import Sequence

from yakoon.base.commands import Command, CommandSet
from yakoon.playground.commands.patterns.cmd_demo_confirm import CmdDemoConfirmSimple

from .cmd_demo_form import CmdDemoFormSimple
from .cmd_demo_subflow import CmdDemoSubflow
from .cmd_demo_validate import CmdDemoValidateSimple


class DemoCommandsPatterns(CommandSet):

    group = "patterns"

    @classmethod
    def commands(cls) -> Sequence[type[Command]]:
        return [
            CmdDemoSubflow,
            CmdDemoValidateSimple,
            CmdDemoFormSimple,
            CmdDemoConfirmSimple,
        ]
