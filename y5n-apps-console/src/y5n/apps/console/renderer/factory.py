from .action import ActionsRenderer
from .action_item import ActionItemRenderer
from .base import BaseRenderer
from .flow import FlowRenderer
from .heading import HeadingRenderer
from .image import ImageRenderer
from .kv import KVRenderer
from .kv_item import KVItemRenderer
from .list import ListRenderer
from .list_item import ListItemRenderer
from .paragraph import ParagraphRenderer
from .rule import RuleRenderer
from .section import SectionRenderer
from .spacer import SpacerRenderer
from .stack import StackRenderer
from .table import TableRenderer
from .text import TextRenderer
from .unknow import UnknownRenderer


class RendererFactory:

    def __init__(self):
        self._types = {
            "text": TextRenderer,
            "rule": RuleRenderer,
            "spacer": SpacerRenderer,
            "list": ListRenderer,
            "list_item": ListItemRenderer,
            "kv": KVRenderer,
            "kv_item": KVItemRenderer,
            "actions": ActionsRenderer,
            "action": ActionItemRenderer,
            "paragraph": ParagraphRenderer,
            "heading": HeadingRenderer,
            "table": TableRenderer,
            "image": ImageRenderer,
            "stack": StackRenderer,
            "flow": FlowRenderer,
            "section": SectionRenderer,
        }

    def create(self, node) -> BaseRenderer:
        cls = self._types.get(node.type)
        if not cls:
            return UnknownRenderer(node, f"No renderer for {node.type}")

        return cls(node)
