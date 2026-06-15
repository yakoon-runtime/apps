import { registerInline, renderInline } from "./core.js";

function createInlineEl(type, tag = "span") {
    const el = document.createElement(tag);
    el.classList.add("inline", `inline-${type}`);
    return el;
}

registerInline("strong", (inline, dispatch, regionEl) => {
    const el = createInlineEl("strong", "strong");

    for (const child of inline.children || []) {
        el.appendChild(renderInline(child, dispatch, regionEl));
    }

    return el;
});