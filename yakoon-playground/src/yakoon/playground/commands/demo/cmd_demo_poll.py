from yakoon.base.commands import Command, Request
from yakoon.base.flow import cooperate, delay, poll, text


class CmdDemoPoll(Command):

    key = "demo.poll"

    async def run(self, request: Request):

        yield text("is running...")
        while True:
            event = yield poll()
            if not event:
                pass
                # yield text(f"Done: {event}")
            else:
                yield text(f"Ihre Eingabe:{event}")

            yield delay(2)
            yield cooperate()
