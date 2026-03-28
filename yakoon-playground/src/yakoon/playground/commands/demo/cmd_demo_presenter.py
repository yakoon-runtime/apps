from yakoon.base.commands import Command, Request
from yakoon.base.flow import show


class CmdDemoPresenter(Command):

    key = "demo.presenter"

    async def run(self, request: Request):

        presenter = await self.get_presenter()
        view = await presenter.render("view_1")
        yield show(view)
