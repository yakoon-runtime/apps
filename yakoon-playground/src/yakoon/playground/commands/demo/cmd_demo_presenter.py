from yakoon.base.flow import show
from yakoon.base.runtime.commands import Command, Request


class CmdDemoPresenter(Command):

    key = "demo.presenter"

    async def run(self, request: Request):

        presenter = await self.get_presenter()
        view = await presenter.render("view_1")
        yield show(view)
