from yakoon.base.capabilities.audit import AuditLogService
from yakoon.base.commands import Command, Request
from yakoon.base.flow import present


class CmdSendMail(Command):

    key = "sendmail"

    async def run(self, request: Request):

        audits = self.container.get(AuditLogService)

        projector = await self.create_projector()
        projection_1 = await projector.project("ask_message")

        audits.audit(f"Mail sent: {projection_1}")

        state = {"message": projection_1}
        projection_2 = await projector.project("show", state=state)
        yield present(projection_2)
