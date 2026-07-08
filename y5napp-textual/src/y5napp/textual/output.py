from __future__ import annotations

from rich.text import Text as RichText
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
    Collapsible,
    DataTable,
    Rule,
    Static,
)


class CopyableStatic(Static):

    can_focus = True

    BINDINGS = [
        ("ctrl+c", "copy", "Copy"),
    ]

    def action_copy(self) -> None:
        parent = self.parent
        while parent is not None:
            if hasattr(parent, "classes") and "projection-group" in parent.classes:
                break
            parent = parent.parent
        if parent is None:
            return
        parts: list[str] = []
        for widget in parent.walk_children():
            if isinstance(widget, CopyableStatic):
                t = widget.content
                if isinstance(t, RichText):
                    parts.append(t.plain)
                elif isinstance(t, str):
                    parts.append(t)
        text = "\n".join(parts)
        if text:
            self.app.copy_to_clipboard(text)


class TextualOutput:

    def __init__(self, container: Widget) -> None:
        self._container = container
        self._widgets: dict[str, Widget] = {}
        self._current_group: Vertical | None = None
        self._current_job_id: str | None = None
        self._pending_input: str | None = None
        self._active_field_value: str | None = None

    @property
    def active_field_value(self) -> str | None:
        return self._active_field_value

    async def view(self, event: ProjectionEvent) -> None:
        self._active_field_value = None

        if event.ctx and event.ctx.echo:
            self._pending_input = event.ctx.echo

        if event.view_params and event.view_params.get("clear"):
            self._clear()

        is_new_job = event.job_id != self._current_job_id
        self._current_job_id = event.job_id

        for op in event.patch.ops:
            match op:
                case PatchReset():
                    if is_new_job:
                        self._start_group()
                        is_new_job = False
                    else:
                        self._replace_group()
                case PatchAppendStructure():
                    if is_new_job:
                        self._start_group()
                        is_new_job = False
                    self._append(op)
                case PatchFinishNode():
                    self._finish(op)

        if self._current_group is not None:
            self._current_group.scroll_visible()

    def _replace_group(self) -> None:
        self._widgets.clear()
        if self._current_group is not None:
            self._current_group.remove_children()
        else:
            group = Vertical(classes="projection-group")
            self._container.mount(group)
            self._current_group = group
        if self._pending_input is not None:
            from rich.text import Text

            line = Text("> ", style="gray")
            line.append(self._pending_input)
            self._current_group.mount(CopyableStatic(line, classes="input-line"))
            self._pending_input = None

    def _start_group(self) -> None:
        self._widgets.clear()
        group = Vertical(classes="projection-group")
        self._container.mount(group)

        if self._pending_input is not None:
            from rich.text import Text

            line = Text("> ", style="gray")
            line.append(self._pending_input)
            group.mount(CopyableStatic(line))
            self._pending_input = None

        self._current_group = group

    def _append(self, op: PatchAppendStructure) -> None:
        for spec in op.nodes:
            widget = self._create_widget(spec)
            self._widgets[spec.id] = widget
            self._mount(widget, spec.parent)

    def _clear(self) -> None:
        self._widgets.clear()
        self._current_group = None
        self._current_job_id = None
        self._container.query(".projection-group").remove()

    def _finish(self, op: PatchFinishNode) -> None:
        pass

    # --------------------------------------------------------

    def _mount(self, widget: Widget, parent_id: str | None) -> None:
        if parent_id:
            parent_widget = self._widgets.get(parent_id)
            if parent_widget is not None:
                if isinstance(parent_widget, Collapsible):
                    parent_widget.call_later(
                        self._mount_collapsible_child, parent_widget, widget
                    )
                    return
                parent_widget.mount(widget)
                return

        group = self._current_group
        if group is not None:
            group.mount(widget)

    def _mount_collapsible_child(self, parent: Collapsible, child: Widget) -> None:
        try:
            contents = parent.query_one("Contents")
            contents.mount(child)
        except Exception:
            parent.mount(child)

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
            case "collapsible":
                return self._make_collapsible(node)
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
            case "pre":
                return self._make_pre(node)
            case "image":
                return self._make_image(node)
            case _:
                return CopyableStatic(f"<{node.type}>", classes="unknown")

    # --------------------------------------------------------

    def _make_text(self, node: Node) -> Static:
        from . import inlines

        text = inlines.render(node.props.get("text", []))
        return CopyableStatic(text)

    def _make_heading(self, node: Node) -> Static:
        from . import inlines

        level = node.props.get("level", 1)
        text = inlines.render(node.props.get("text", []))
        return CopyableStatic(text, classes=f"heading h{level}")

    def _make_list_item(self, node: Node) -> Static:
        from rich.text import Text

        from . import inlines

        bullet = Text(" \u2022 ", style="bold")
        bullet.append(inlines.render(node.props.get("text", [])))
        return CopyableStatic(bullet, classes="list-item")

    def _make_kv_item(self, node: Node) -> Horizontal:
        from . import inlines

        key = node.props.get("key", "")
        value = inlines.render(node.props.get("value", []))
        return Horizontal(
            CopyableStatic(key, classes="kv-key"),
            CopyableStatic(value, classes="kv-value"),
            classes="kv-row",
        )

    def _make_table(self, node: Node) -> DataTable:
        dt = DataTable()
        columns = node.props.get("columns", [])
        for col in columns:
            title = col.get("title") if isinstance(col, dict) else col.title
            dt.add_column(title)
        rows = node.props.get("rows", [])
        for row in rows:
            dt.add_row(*row)
        return dt

    def _make_action(self, node: Node) -> Button:
        label = node.props.get("label", "")
        action_id = node.props.get("id")
        btn = Button(label)
        return btn

    def _make_fields(self, node: Node) -> Widget:
        from rich.text import Text

        title = node.props.get("title") or node.props.get("name", "")
        fields = node.props.get("fields", [])

        lines = []
        error_line = None
        if title:
            lines.append(Text(f"{title}", style="bold"))

        found_active = False
        for f in fields:
            label = f.get("title") or f.get("name", "?")
            value = f.get("value")
            state = f.get("state")
            required = f.get("required", False)
            error = f.get("error")
            req = " *" if required else ""

            if state == "active":
                self._active_field_value = value or ""
                line = (
                    Text(f"\u25b6 {label}{req}: {value}", style="bold")
                    if value
                    else Text(f"\u25b6 {label}{req}: ", style="bold")
                )
                found_active = True
            elif state == "done":
                line = Text(f"  {label}{req}: {value}")
            elif state == "idle":
                line = Text(f"  {label}{req}:", style="dim")
            elif not found_active and value is None:
                self._active_field_value = ""
                line = Text(f"\u25b6 {label}{req}: ", style="bold")
                found_active = True
            elif value is not None:
                line = Text(f"  {label}{req}: {value}")
            else:
                line = Text(f"  {label}{req}:", style="dim")
            lines.append(line)
            if error and state == "active":
                error_line = f"  \u26a0 {error}"

        children: list[Widget] = [CopyableStatic(Text("\n").join(lines))]
        if error_line:
            children.append(Static(error_line, classes="field-error"))
        return Vertical(*children, classes="fields")

    def _make_pre(self, node: Node) -> Static:
        code = node.props.get("code", "")
        return CopyableStatic(code, classes="code-block")

    def _make_image(self, node: Node) -> Static:
        alt = node.props.get("alt") or node.props.get("ref", "")
        return CopyableStatic(f"[img] {alt}", classes="image")

    def _make_collapsible(self, node: Node) -> Collapsible:
        from . import inlines

        title = inlines.render(node.props.get("title", []))
        expanded = node.props.get("expanded", False)
        return Collapsible(
            title=title,
            collapsed=not expanded,
            collapsed_symbol="[+]",
            expanded_symbol="[-]",
        )
