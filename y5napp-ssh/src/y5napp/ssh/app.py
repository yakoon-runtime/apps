from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import asyncssh
from y5n.base.projection.transfer import (
    PatchAppendStructure,
    PatchFinishNode,
    PatchReset,
)
from y5n.base.runtime import Event
from y5ntrans.websocket.client import WebSocketClientTransport


def _render_inline(inlines):
    if not inlines:
        return ""
    if isinstance(inlines, str):
        return inlines

    parts = []
    for item in inlines:
        t = item.get("type", "")
        if t == "text":
            parts.append(item.get("text", ""))
        elif t in ("strong", "em", "mark", "underline"):
            parts.append(_render_inline(item.get("children", [])))
        elif t == "code":
            parts.append(item.get("text", ""))
        elif t == "cmd":
            parts.append(item.get("text", ""))
        elif t == "arg":
            parts.append(item.get("text", ""))
        elif t == "select":
            parts.append(item.get("text", ""))
        elif t == "link":
            label = _render_inline(item.get("children", []))
            href = item.get("href", "")
            parts.append(f"{label} ({href})" if href else label)
        elif t == "break":
            parts.append("\n")
        elif t == "space":
            parts.append(" " * item.get("count", 1))
        else:
            parts.append(item.get("text", item.get("label", "")))

    return "".join(parts)


def _render_block(node):
    props = node.props
    t = node.type

    if t == "text":
        return _render_inline(props.get("text", ""))

    if t == "paragraph":
        return _render_inline(props.get("text", ""))

    if t == "heading":
        level = props.get("level", 1)
        return f"{'#' * level} {_render_inline(props.get('text', ''))}"

    if t == "list_item":
        return f"  \u2022 {_render_inline(props.get('text', ''))}"

    if t == "action":
        action = props.get("action")
        if action:
            return action.get("label", "")
        return ""

    if t in ("action_item",):
        return props.get("label", "")

    if t == "kv_item":
        return f"{props.get('key', '')} = {_render_inline(props.get('text', ''))}"

    if t == "rule":
        return "\u2014"

    if t == "image":
        return props.get("alt", "")

    if t in ("list", "kv", "actions", "stack", "section", "flow", "spacer"):
        return ""

    return props.get("text", props.get("title", ""))


def extract_text(event):
    lines = []

    for op in event.patch.ops:
        if isinstance(op, PatchReset):
            lines.clear()
        elif isinstance(op, PatchFinishNode):
            text = _render_block(op)
            if text:
                lines.append(text)

    return "\n".join(lines)


class SSHSession(asyncssh.SSHServerSession):

    def __init__(self, runtime_url: str):
        self._runtime_url = runtime_url
        self._transport: WebSocketClientTransport | None = None
        self._connection = None
        self._buffer = ""
        self._chan = None

    def connection_made(self, chan):
        self._chan = chan

    def shell_requested(self):
        return True

    def pty_requested(self, term_type, term_size, term_modes):
        return True

    def session_started(self):
        asyncio.create_task(self._run())

    def data_received(self, data, datatype):
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if line:
                asyncio.create_task(self._dispatch(line))

    def eof_received(self):
        asyncio.create_task(self._close())
        return True

    def signal_received(self, signal: str):
        if signal == "INT":
            asyncio.create_task(self._close())

    async def _run(self):
        self._transport = WebSocketClientTransport(self._runtime_url)
        self._connection = await self._transport.connect(on_emit=self._on_projection)
        self._write("shell$ ")

    async def _on_projection(self, event):
        text = extract_text(event)
        if text:
            self._write(text + "\n")
        if event.is_final():
            self._write("shell$ ")

    async def _dispatch(self, line):
        if self._connection:
            await self._connection.dispatch(Event.from_raw(line))

    async def _close(self):
        if self._transport:
            await self._transport.close()
        if self._chan:
            self._chan.close()

    def _write(self, text):
        if self._chan:
            self._chan.write(text)


class SSHServer(asyncssh.SSHServer):

    def __init__(self, runtime_url: str):
        self._runtime_url = runtime_url

    def begin_auth(self, username):
        return False

    def session_requested(self):
        return SSHSession(self._runtime_url)


def run():
    parser = argparse.ArgumentParser(description="SSH bridge to Runtime")
    parser.add_argument(
        "--runtime",
        default="ws://localhost:9100",
        help="WebSocket URL of the Runtime (default: ws://localhost:9100)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8022,
        help="SSH server port (default: 8022)",
    )
    args = parser.parse_args()

    async def _run():
        BASE_DIR = Path(__file__).resolve().parent
        KEY_PATH = BASE_DIR / "ssh_keys/ssh_host_key"

        await asyncssh.create_server(
            lambda: SSHServer(args.runtime),
            "",
            args.port,
            server_host_keys=[str(KEY_PATH)],
        )

        print(f"SSH server running on port {args.port} \u2192 {args.runtime}")

        await asyncio.Future()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
