from yakoon.base.capabilities.audit import AuditLogService
from yakoon.base.runtime import Command, Request, Session


class CmdSendMail(Command):

    key = "sendmail"

    async def run(self, session: Session, request: Request) -> None:  # noqa: ARG002

        presenter = await self.get_presenter(session)
        audits = self.services.get(AuditLogService)

        message = await presenter.present("ask_message")

        audits.audit(f"Mail sent: {message}")
        await presenter.present("show", message=message)
