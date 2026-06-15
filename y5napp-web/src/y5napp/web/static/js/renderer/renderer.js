import { renderBlock } from "./block/core.js";

// block registrations (side effects)
import "./block/text.js";
import "./block/list.js";
import "./block/list_item.js";
import "./block/kv.js";
import "./block/kv_item.js";
import "./block/rule.js";
import "./block/fields.js";
import "./block/actions.js";
import "./block/paragraph.js";
import "./block/heading.js";
import "./block/section.js";
import "./block/stack.js";
import "./block/flow.js";
import "./block/image.js";
import "./block/spacer.js";
import "./block/collapsible.js";
import "./block/table.js";

// inline registrations (side effects)
import "./inline/text.js";
import "./inline/code.js";
import "./inline/cmd.js";
import "./inline/select.js";
import "./inline/action.js";
import "./inline/strong.js";
import "./inline/em.js";
import "./inline/underline.js";
import "./inline/mark.js";
import "./inline/br.js";
import "./inline/link.js";
import "./inline/arg.js";
import "./inline/space.js";


export class Renderer {

    static from(el) {
        const root = el.closest('[data-renderer="true"]');
        return root?._renderer || null;
    }

    constructor(container, dispatch) {
        this.container = container;
        this.dispatch = dispatch;

        this.nodes = {};
        this.children = {};
    }

    apply(payload) {
        const patch = payload.patch;

        for (const op of patch.ops) {
            this.handle(op);
        }

        if (patch.final) {
            this.render();
        }
    }

    handle(op) {
        if (op.op === "reset") {
            this.nodes = {};
            this.children = {};
        }

        if (op.op === "append_structure") {
            console.log("append_structure");
            for (const n of op.nodes) {
                this.nodes[n.id] = n;

                if (n.parent) {
                    if (!this.children[n.parent]) {
                        this.children[n.parent] = [];
                    }
                    this.children[n.parent].push(n.id);
                }
            }
        }
    }

    render() {
        const root = Object.values(this.nodes).find(n =>
            n.parent?.endsWith(":root")
        );

        if (!root) return;

        this.container.innerHTML = "";
        this.renderNode(root.parent, this.container);
    }

    renderNode(parentId, container) {
        const kids = this.children[parentId] || [];

        for (const id of kids) {
            const node = this.nodes[id];

            const el = this.createElement(node);
            container.appendChild(el);

            this.renderNode(id, el);
        }
    }

    createElement(node) {
        return renderBlock(node, this.dispatch, this);
    }

    openInteraction(region, command) {
        if (region.dataset.open === command) {
            region.innerHTML = "";
            delete region.dataset.open;
            return;
        }

        region.innerHTML = "";
        region.dataset.open = command;

        this.dispatch.command(command, {}, region);
    }
}