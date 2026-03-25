from collections.abc import Sequence

from yakoon.base.api import Command, CommandSet
from yakoon.crm.customer.commands.cmd_create import CmdCustomerCreate
from yakoon.crm.customer.commands.cmd_store import CmdCustomerStore
from yakoon.crm.customer.commands.cmd_validate import CmdCustomerValidate


class CrmCustomerCommands(CommandSet):

    group = "customer"

    @classmethod
    def commands(cls) -> Sequence[type[Command]]:
        return [
            CmdCustomerCreate,
            CmdCustomerStore,
            CmdCustomerValidate,
        ]
