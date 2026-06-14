import { createElement, findRegion, findScope } from "../dom.js";
import { collectFields, buildCommand } from "../cmd.js";

export function renderActions(node, dispatch, container) {

    for (const action of node.props.actions || []) {
        const btn = createElement("button", "action-button");
        btn.textContent = action.label;

        btn.onclick = (e) => {
            const region = findRegion(e.currentTarget);
            if (!region) return;

            if (action.scope) {
                const root = findScope(e.currentTarget, action.scope);

                const data = collectFields(root);
                const cmd = buildCommand(action.command, data);
                dispatch.command(cmd, {}, region);
            } else {
                dispatch.command(action.command, {}, region);
            }
        };

        container.appendChild(btn);
    }
}