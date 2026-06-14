import { registerInline, renderInline } from "./core.js";

function createInlineEl(type, tag = "span") {
    const el = document.createElement(tag);
    el.classList.add("inline", `inline-${type}`);
    return el;
}

registerInline("mark", (inline, dispatch, regionEl) => {
    const el = createInlineEl("mark", "mark");

    if (inline.variant) {
        el.classList.add(`mark-${inline.variant}`);
    }

    for (const child of inline.children || []) {
        el.appendChild(renderInline(child, dispatch, regionEl));
    }

    return el;
});