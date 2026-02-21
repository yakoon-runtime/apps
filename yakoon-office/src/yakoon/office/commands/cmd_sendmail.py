from yakoon.base.commands.command import Command
from yakoon.base.commands.request import Request
from yakoon.base.ports import AuditLogService
from yakoon.base.runtime.session import Session


class CmdSendMail(Command):

    key = "sendmail"

    async def run(self, session: Session, request: Request) -> None:  # noqa: ARG002

        presenter = await self.get_presenter(session)
        audits = self.services.get(AuditLogService)

        message = await presenter.inputs.ask("ask_message")

        await audits.audit(f"Mail sent: {message}")
        await presenter.views.emit("send_mail", message=message)
