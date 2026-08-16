from .base import BaseInlineRenderer, _get


class TextInlineRenderer(BaseInlineRenderer):

    def render(self) -> str:
        return _get(self.node, "text", "")
