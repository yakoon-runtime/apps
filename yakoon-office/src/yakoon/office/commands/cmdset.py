from collections.abc import Sequence

from yakoon.base.runtime import Command, CommandSet
from yakoon.office.commands.cmd_sendmail import CmdSendMail


class MailingCommands(CommandSet):

    group = "system"

    @classmethod
    def commands(cls) -> Sequence[type[Command]]:
        return [
            CmdSendMail,
        ]
