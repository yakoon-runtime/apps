import { registerBlock } from "./core.js";
import { renderInline } from "../inline/core.js";

registerBlock("collapsible", (node, dispatch, renderer) => {
    const el = document.createElement("div");
    el.classList.add("collapsible");

    const header = document.createElement("div");
    header.classList.add("collapsible-header");

    const icon = document.createElement("span");
    icon.classList.add("collapsible-icon");
    icon.textContent = "[+]";

    const title = document.createElement("span");
    title.classList.add("collapsible-title");
    for (const inline of node.props.title || []) {
        title.appendChild(renderInline(inline, dispatch, el));
    }

    header.appendChild(icon);
    header.appendChild(title);

    header.onclick = () => {
        el.classList.toggle("collapsed");
        icon.textContent = el.classList.contains("collapsed") ? "[+]" : "[−]";
    };

    el.appendChild(header);

    if (!node.props.expanded) {
        el.classList.add("collapsed");
    }

    return el;
});
