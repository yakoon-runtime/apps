from __future__ import annotations

from y5n.base.projection.transfer import (
    PatchAppendStructure,
    PatchFinishNode,
    PatchReset,
    ProjectionEvent,
)
from y5n.base.projection.transfer.node import Node

from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import (
    Button,
    DataTable,
    Rule,
    Static,
)


class TextualOutput:

    def __init__(self, container: Widget) -> None:
        self._container = container
        self._widgets: dict[str, Widget] = {}

    async def view(self, event: ProjectionEvent) -> None:
        for op in event.patch.ops:
            match op:
                case PatchReset():
                    self._reset()
                case PatchAppendStructure():
                    self._append(op)
                case PatchFinishNode():
                    self._finish(op)

    # --------------------------------------------------------

    def _reset(self) -> None:
        self._widgets.clear()
        self._container.remove_children()

    def _append(self, op: PatchAppendStructure) -> None:
        for spec in op.nodes:
            widget = self._create_widget(spec)
            self._widgets[spec.id] = widget
            self._mount(widget, spec.parent)

    def _finish(self, op: PatchFinishNode) -> None:
        pass

    # --------------------------------------------------------

    def _mount(self, widget: Widget, parent_id: str | None) -> None:
        if parent_id:
            parent_widget = self._widgets.get(parent_id)
            if parent_widget is not None:
                parent_widget.mount(widget)
                return

        self._container.mount(widget)

    # --------------------------------------------------------

    def _create_widget(self, node: Node) -> Widget:
        match node.type:
            case "text" | "paragraph":
                return self._make_text(node)
            case "heading":
                return self._make_heading(node)
            case "rule":
                return Rule()
            case "spacer":
                return Vertical(classes="spacer")
            case "list":
                return Vertical(classes="list")
            case "list_item":
                return self._make_list_item(node)
            case "section":
                return Vertical(classes="section")
            case "stack":
                return Vertical(classes="stack")
            case "flow":
                return Horizontal(classes="flow")
            case "kv":
                return Vertical(classes="kv")
            case "kv_item":
                return self._make_kv_item(node)
            case "table":
                return self._make_table(node)
            case "actions":
                return Horizontal(classes="actions")
            case "action":
                return self._make_action(node)
            case "fields":
                return self._make_fields(node)
            case "image":
                return self._make_image(node)
            case _:
                return Static(f"<{node.type}>", classes="unknown")

    # --------------------------------------------------------

    def _make_text(self, node: Node) -> Static:
        from . import inlines

        text = inlines.render(node.props.get("text", []))
        return Static(text)

    def _make_heading(self, node: Node) -> Static:
        from . import inlines

        level = node.props.get("level", 1)
        text = inlines.render(node.props.get("text", []))
        return Static(text, classes=f"heading h{level}")

    def _make_list_item(self, node: Node) -> Static:
        from rich.text import Text

        from . import inlines

        bullet = Text(" \u2022 ", style="bold")
        bullet.append(inlines.render(node.props.get("text", [])))
        return Static(bullet, classes="list-item")

    def _make_kv_item(self, node: Node) -> Horizontal:
        from . import inlines

        key = node.props.get("key", "")
        value = inlines.render(node.props.get("value", []))
        return Horizontal(
            Static(key, classes="kv-key"),
            Static(value, classes="kv-value"),
            classes="kv-row",
        )

    def _make_table(self, node: Node) -> DataTable:
        dt = DataTable()
        headers = node.props.get("headers", [])
        if headers:
            for h in headers:
                dt.add_column(h)
        rows = node.props.get("rows", [])
        for row in rows:
            dt.add_row(*row)
        return dt

    def _make_action(self, node: Node) -> Button:
        label = node.props.get("label", "")
        action_id = node.props.get("id")
        btn = Button(label, id=node.id)
        return btn

    def _make_fields(self, node: Node) -> Static:
        return Static("<fields>", classes="fields-placeholder")

    def _make_image(self, node: Node) -> Static:
        alt = node.props.get("alt") or node.props.get("ref", "")
        return Static(f"[img] {alt}", classes="image")
