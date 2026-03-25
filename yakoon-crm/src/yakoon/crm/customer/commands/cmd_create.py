from yakoon.base.api import Command, Request


class CmdCustomerCreate(Command):

    key = "customer-create"

    async def run(self, request: Request) -> None:  # noqa: ARG002

        wf = self.services.get(WorkflowPublic)
        if not self.context:
            raise RuntimeError("Context cannot be None.")

        controller_id = self.context.controller.id

        wf.start(
            session,
            controller_id,
            command_key=self.key,
            enqueue_first=True,
        )
