from .base import BaseInlineRenderer, _get


class BreakInlineRenderer(BaseInlineRenderer):

    def render(self) -> str:
        count = int(_get(self.node, "count", 1))
        return "\n" * count
