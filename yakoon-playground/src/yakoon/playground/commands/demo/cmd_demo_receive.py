from yakoon.base.commands import Command, Request
from yakoon.base.flow import delay, receive, text


class CmdDemoReceiveSimple(Command):

    key = "demo.receive.simple"

    async def run(self, request: Request):

        yield text("is running...")
        while True:
            event = yield receive()
            if not event:
                yield delay(5)
            else:
                yield text(f"Ihre Eingabe: {event}")
