from .base import BaseInlineRenderer, _get
from .inline import render_inline


class UnderlineInlineRenderer(BaseInlineRenderer):

    def render(self) -> str:
        children = _get(self.node, "children") or []
        inner = render_inline(children)

        # Terminal unterstützt kein underline
        return inner
