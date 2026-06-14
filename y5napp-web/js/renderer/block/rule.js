import { registerBlock } from "./core.js";
import { createElement } from "../../dom.js";

registerBlock("rule", (node) => {
    const el = createElement("hr");

    el.classList.add("rule");

    const style = node.props.style || "normal";
    el.classList.add(`rule-${style}`);

    return el;
});