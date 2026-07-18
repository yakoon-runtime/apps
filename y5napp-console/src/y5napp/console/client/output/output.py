# output.py

from __future__ import annotations

import asyncio
from collections.abc import Callable

from y5n.base.document.percept.perceptual import PerceptualStream
from y5n.base.document.transfer import (
    PatchAppendStructure,
    PatchFinishNode,
    PatchReset,
)

from ..renderer import RendererFactory


class Node:
    def __init__(self, *, id: str, type: str, parent: str | None, props: dict):
        self.id = id
        self.type = type
        self.parent = parent
        self.props = props


class ConsoleOutput:

    def __init__(self, terminal):
        self.terminal = terminal
        self._nodes: dict[str, Node] = {}
        self._builder = RendererFactory()
        self.on_finished: Callable | None = None

        self._stream = PerceptualStream(
            on_text=self._on_text,
            on_block_finished=self._on_block_finish,
            on_stream_finished=self._handle_finished,
        )

    # ------------------------
    # Public API
    # ------------------------

    async def view(self, event):

        for op in event.patch.ops:

            # RESET
            if isinstance(op, PatchReset):
                self._nodes.clear()
                continue

            # STRUCTURE
            if isinstance(op, PatchAppendStructure):
                for spec in op.nodes:
                    node = Node(
                        id=spec.id,
                        type=spec.type,
                        parent=spec.parent,
                        props=spec.props,
                    )
                    self._nodes[node.id] = node
                continue

            # FINISH
            if isinstance(op, PatchFinishNode):

                node = self._nodes.get(op.block_id)
                if not node:
                    continue

                renderer = self._builder.create(node)

                text = renderer.render()
                if text:
                    self._stream.push_block(node.id, "text", text)

                self._stream.finish_block(node.id)

    # ------------------------
    # Perception callbacks
    # ------------------------

    def _on_text(self, node_id, key, chunk):
        self.terminal.write(chunk)

    def _on_block_finish(self, node_id):
        pass
        # self.terminal.write("_on_block_finish " + node_id)
        # self.terminal.new_line()

    def _handle_finished(self):
        if self.on_finished:
            self.on_finished()

    # ------------------------
    # Stream Loop
    # ------------------------

    async def run(self):

        while True:
            self._stream.step(self._stream.FRAME_INTERVAL)
            await asyncio.sleep(0.005)
