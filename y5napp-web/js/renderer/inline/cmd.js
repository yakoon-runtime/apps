import { registerInline, renderInline } from "./core.js";

function createInlineEl(type, tag = "span") {
    const el = document.createElement(tag);
    el.classList.add("inline", `inline-${type}`);
    return el;
}

registerInline("cmd", (inline, dispatch, regionEl) => {
    const el = createInlineEl("cmd");

    for (const child of inline.children || []) {
        el.appendChild(renderInline(child, dispatch, regionEl));
    }

    el.onclick = () => {
        dispatch.newTurn(inline.command);
    };

    return el;
});