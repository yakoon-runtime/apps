from .base import BaseRenderer


class ImageRenderer(BaseRenderer):

    def __init__(self, node):
        self.node = node

    def render(self) -> str:
        src = self.node.props.get("src")
        alt = self.node.props.get("alt") or "unnamed"
        return f"[Image: {alt} - {src}]\n"
