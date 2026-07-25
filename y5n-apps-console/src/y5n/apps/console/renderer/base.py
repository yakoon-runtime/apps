from typing import Protocol


class BaseRenderer(Protocol):

    def render(self) -> str: ...
