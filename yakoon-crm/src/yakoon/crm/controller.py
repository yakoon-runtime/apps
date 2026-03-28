from __future__ import annotations

from collections.abc import Sequence

from yakoon.base.commands import CommandSet
from yakoon.base.controllers import Controller, ResourceReferences
from yakoon.crm.customer.commands.cmdset import CrmCustomerCommands


class CrmCustomerCoreController(Controller):
    """Controller for CRM customer management.

    Provides:
        - Customer-related commands
        - Customer workflows
        - Templates and workflows under yakoon.crm.customer:customer
    """

    id: str = "crm-customer"

    resources = ResourceReferences(
        package="yakoon.crm.customer",
    )

    @property
    def commandsets(self) -> Sequence[type[CommandSet]]:
        """Command sets exported by this controller."""
        return (CrmCustomerCommands,)
