from .base import BaseInlineRenderer, _get
from .inline import render_inline


class CodeInlineRenderer(BaseInlineRenderer):

    def render(self) -> str:
        inner = render_inline(_get(self.node, "children") or [])
        return f"`{inner}`"
