import { registerInline } from "./core.js";
import { findRegion } from "../../dom.js";

function createInlineEl(type, tag = "span") {
    const el = document.createElement(tag);
    el.classList.add("inline", `inline-${type}`);
    return el;
}

registerInline("action", (inline, dispatch) => {
    const el = createInlineEl("action");

    el.textContent = inline.text;

    el.onclick = () => {
        const region = findRegion(el);
        if (!region) return;

        dispatch.command(inline.command, inline.payload || {}, region);
    };

    return el;
});