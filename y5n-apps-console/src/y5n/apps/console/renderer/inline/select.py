from .base import BaseInlineRenderer, _get
from .inline import render_inline


class SelectInlineRenderer(BaseInlineRenderer):

    def render(self) -> str:
        children = _get(self.node, "children") or []
        return render_inline(children)
