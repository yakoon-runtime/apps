from yakoon.base.commands import Command, Request
from yakoon.base.flow import delay, receive, write


class CmdDemoReceiveSimple(Command):

    key = "demo.receive.simple"

    async def run(self, request: Request):

        yield write("is running...")
        while True:
            event = yield receive()
            if not event:
                yield delay(5)
            else:
                yield write(f"Ihre Eingabe: {event}")
