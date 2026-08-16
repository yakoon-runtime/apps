import { registerInline, renderInline } from "./core.js";

function createInlineEl(type, tag = "span") {
    const el = document.createElement(tag);
    el.classList.add("inline", `inline-${type}`);
    return el;
}

registerInline("cmd", (inline, dispatch, regionEl) => {
    const el = createInlineEl("cmd");

    if (inline.variant === "global") {
        el.classList.add("cmd-global");
    } else if (inline.variant === "usage") {
        el.classList.add("cmd-usage");
    } else if (inline.navigable && inline.resolvable === false) {
        el.classList.add("cmd-container");
    } else {
        el.classList.add("cmd-executable");
    }

    for (const child of inline.children || []) {
        el.appendChild(renderInline(child, dispatch, regionEl));
    }

    el.onclick = () => {
        dispatch.newTurn(inline.command);
    };

    return el;
});