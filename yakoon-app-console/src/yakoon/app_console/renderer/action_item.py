from .base import BaseRenderer


class ActionItemRenderer(BaseRenderer):

    def __init__(self, node):
        self.node = node

    def render(self) -> str:

        action = self.node.props.get("action")
        if not action:
            return "[action]"

        label = action.label or "action"
        return f"[{label}]\n"
