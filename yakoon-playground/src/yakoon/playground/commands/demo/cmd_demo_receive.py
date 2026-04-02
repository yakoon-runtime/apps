from yakoon.base.commands import Command, Request
from yakoon.base.flow import delay, receive
from yakoon.base.flow.patterns import write_text


class CmdDemoReceiveSimple(Command):

    key = "demo.receive.simple"

    async def run(self, request: Request):

        yield write_text("is running...")
        while True:
            event = yield receive()
            if not event:
                yield delay(5)
            else:
                yield write_text(f"Ihre Eingabe: {event}")
