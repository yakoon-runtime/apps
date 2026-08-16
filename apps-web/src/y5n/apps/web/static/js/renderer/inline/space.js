import { registerInline } from "./core.js";

registerInline("space", (inline) => {
    const count = inline.count || 1;
    const el = document.createElement("span");
    el.classList.add("inline", "inline-space");
    el.textContent = "\u00A0".repeat(count);
    return el;
});
