from .base import BaseInlineRenderer, _get
from .inline import render_inline


class MarkInlineRenderer(BaseInlineRenderer):

    def render(self) -> str:
        children = _get(self.node, "children") or []
        inner = render_inline(children)

        variant = _get(self.node, "variant")

        if variant == "important":
            return f"[!] {inner}"
        if variant == "error":
            return f"[ERROR] {inner}"
        if variant == "success":
            return f"[OK] {inner}"

        return inner
