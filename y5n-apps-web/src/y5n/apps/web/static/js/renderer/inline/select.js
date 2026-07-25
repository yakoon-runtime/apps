import { registerInline, renderInline } from "./core.js";

function createInlineEl(type, tag = "span") {
    const el = document.createElement(tag);
    el.classList.add("inline", `inline-${type}`);
    return el;
}
registerInline("select", (inline, dispatch, regionEl) => {
    const el = createInlineEl("select");

    for (const child of inline.children || []) {
        el.appendChild(renderInline(child, dispatch, regionEl));
    }

    el.onclick = () => {
        const field = el.closest(".field-block");
        if (!field) return;

        const input = field.querySelector("input");
        if (!input) return;

        input.value = el.textContent;
        field.dataset.value = inline.value;

        const region = el.closest("[data-region-id]");
        if (region) region.innerHTML = "";
    };

    return el;
});