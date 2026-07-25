import { registerBlock } from "./core.js";

registerBlock("spacer", (node) => {
    const el = document.createElement("div");
    el.classList.add("spacer");
    const size = node.props.size || 1;
    for (let i = 0; i < size; i++) {
        el.appendChild(document.createElement("br"));
    }
    return el;
});
