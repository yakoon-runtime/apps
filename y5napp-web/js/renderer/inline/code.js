import { registerInline, renderInline } from "./core.js";

function createInlineEl(type, tag = "span") {
    const el = document.createElement(tag);
    el.classList.add("inline", `inline-${type}`);
    return el;
}

registerInline("code", (inline, dispatch, regionEl) => {
    const el = createInlineEl("code", "code");

    for (const child of inline.children || []) {
        el.appendChild(renderInline(child, dispatch, regionEl));
    }

    return el;
});