from .base import BaseInlineRenderer, _get


class UnknownInlineRenderer(BaseInlineRenderer):

    def __init__(self, node, message=None, strict=False):
        self.node = node
        self.message = message
        self.strict = strict

    def render(self) -> str:
        t = _get(self.node, "type", "unknown")

        if self.strict:
            raise ValueError(f"Unknown inline type: {t}")

        return f"[{t}]"
