from yakoon.base import ports
from yakoon.base.commands import (
    Command,
    CommandKind,
    CommandVisibility,
    Request,
)


class CmdCustomerValidate(Command):

    key = "wf:crm.customer.validate"

    kind = CommandKind.WORKFLOW
    visibility = CommandVisibility.INTERNAL
    requires_workflow = True

    async def run(self, request: Request) -> None:  # noqa: ARG002

        wf = self.services.get(ports.WorkflowPublic)
        batch_id = self.ctx.batch_id
        batch = wf.runtime(session).get(
            batch_id
        )  # TODO: hier brauchen wir eine Methode aus public. get ba

        mail = batch.values.get("customer.mail")
        mail_opt_in = batch.values.get("customer.mail_opt_in")

        state = "unknown"

        if mail_opt_in in {"yes", "true", "1"}:
            if mail and mail.endswith("@enterprise.com"):
                state = "save"

        wf.set_value(session, batch_id, "validate.state", state)
