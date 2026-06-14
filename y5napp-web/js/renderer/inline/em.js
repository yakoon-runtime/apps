import { registerInline, renderInline } from "./core.js";

function createInlineEl(type, tag = "span") {
    const el = document.createElement(tag);
    el.classList.add("inline", `inline-${type}`);
    return el;
}

registerInline("em", (inline, dispatch, regionEl) => {
    const el = createInlineEl("em", "em");

    for (const child of inline.children || []) {
        el.appendChild(renderInline(child, dispatch, regionEl));
    }

    return el;
});