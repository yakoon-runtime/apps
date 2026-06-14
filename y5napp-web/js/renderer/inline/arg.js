import { registerInline, renderInline } from "./core.js";

registerInline("arg", (inline, dispatch, regionEl) => {
    const el = document.createElement("span");
    el.classList.add("inline", "inline-arg");
    for (const child of inline.children || []) {
        el.appendChild(renderInline(child, dispatch, regionEl));
    }
    return el;
});
