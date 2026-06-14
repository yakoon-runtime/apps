from .base import BaseRenderer


class RuleRenderer(BaseRenderer):

    def __init__(self, node):
        self.node = node

    def render(self) -> str:
        style = self.node.props.get("style", "normal")

        if style == "strong":
            return "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        if style == "subtle":
            return "------------------------\n"

        return "────────────────────────\n"
