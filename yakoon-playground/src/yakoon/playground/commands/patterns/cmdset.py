from collections.abc import Sequence

from yakoon.base.commands import Command, CommandSet
from yakoon.playground.commands.patterns.cmd_demo_form_select import CmdDemoFormSelect

from .cmd_demo_form_simple import CmdDemoFormSimple
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
            CmdDemoFormSelect,
        ]
