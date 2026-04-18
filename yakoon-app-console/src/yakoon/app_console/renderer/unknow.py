from .base import BaseRenderer


class UnknownRenderer(BaseRenderer):

    def __init__(self, node, error: str):
        self.node = node
        self.error = error

    def render(self) -> str:
        t = self.node.type
        return f"[unknown block: {t} | {self.error}]\n"
