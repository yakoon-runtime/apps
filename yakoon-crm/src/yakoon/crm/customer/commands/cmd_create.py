from yakoon.base import ports
from yakoon.base.commands.command import Command
from yakoon.base.commands.request import Request
from yakoon.base.runtime.session import Session


class CmdCustomerCreate(Command):

    key = "customer-create"

    async def run(self, session: Session, request: Request) -> None:  # noqa: ARG002

        wf = self.services.get(ports.WorkflowPublic)
        if not self.context:
            raise RuntimeError("Context cannot be None.")

        controller_id = self.context.controller.id

        wf.start(
            session,
            controller_id,
            command_key=self.key,
            enqueue_first=True,
        )
