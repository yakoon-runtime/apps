from .base import BaseInlineRenderer, _get
from .inline import render_inline


class LinkInlineRenderer(BaseInlineRenderer):

    def render(self) -> str:
        children = _get(self.node, "children") or []
        label = render_inline(children)

        href = _get(self.node, "href")
        if not href:
            return label  # bewusst: kein kaputter Link

        return f"{label} ({href})"
