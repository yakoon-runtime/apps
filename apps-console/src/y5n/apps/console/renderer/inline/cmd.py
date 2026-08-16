from .base import BaseInlineRenderer, _get
from .inline import render_inline


class CmdInlineRenderer(BaseInlineRenderer):

    def render(self) -> str:
        children = _get(self.node, "children") or []
        label = render_inline(children)

        # leichte visuelle Markierung
        return f"{label}"
