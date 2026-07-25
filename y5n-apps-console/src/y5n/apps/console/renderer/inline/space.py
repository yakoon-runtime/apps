from .base import BaseInlineRenderer, _get


class SpaceInlineRenderer(BaseInlineRenderer):

    def render(self) -> str:
        count = int(_get(self.node, "count", 1))
        return " " * count
