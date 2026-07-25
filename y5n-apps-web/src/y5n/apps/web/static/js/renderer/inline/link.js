import { registerInline, renderInline } from "./core.js";

registerInline("link", (inline, dispatch, regionEl) => {
    const el = document.createElement("a");

    el.classList.add("inline", "inline-link");

    el.href = inline.href;
    el.target = "_blank";
    el.rel = "noopener noreferrer";

    for (const child of inline.children || []) {
        el.appendChild(renderInline(child, dispatch, regionEl));
    }

    return el;
});