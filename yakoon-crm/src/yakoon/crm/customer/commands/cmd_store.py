from uuid import uuid4

from yakoon.base.api import Command, Request
from yakoon.base.api.command import CommandKind, CommandVisibility
from yakoon.base.capabilities.audit import AuditLogService


class CmdCustomerStore(Command):

    key = "wf:crm.customer.store"

    kind = CommandKind.WORKFLOW
    visibility = CommandVisibility.INTERNAL

    requires_workflow = True

    async def run(self, request: Request) -> None:  # noqa: ARG002

        audits = self.services.get(AuditLogService)

        first = request.option("first_name")
        last = request.option("last_name")
        mail_opt_in = request.option("mail_opt_in")
        mail = request.option("mail")

        if not first or not last:
            raise ValueError("Missing required: --first, --last")

        # Optional: Konsistenz
        if mail_opt_in in {"yes", "true", "1"} and not mail:
            raise ValueError("mail_opt_in=yes requires --mail")

        customer_id = f"CUST-{uuid4().hex[:8]}"

        # “Ernte”: audit + event
        audits.audit(f"Customer created: {first} {last} id={customer_id}")
